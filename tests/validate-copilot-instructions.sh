#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WRAPPER="$REPO_ROOT/scripts/validate-copilot-instructions.sh"
CANONICAL_VALIDATOR="$REPO_ROOT/scripts/validate-ai-instructions.sh"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-copilot-instructions.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

write_valid_repo() {
    local target_dir="$1"

    mkdir -p "$target_dir/.github"
    cp "$REPO_ROOT/.markdownlint.json" "$target_dir/.markdownlint.json"

    cat >"$target_dir/AGENTS.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Repository Runtime Instructions

## Runtime Safety

- Preserve existing work and validate executable changes.
EOF

    cat >"$target_dir/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Code Review Profile

Review the complete diff and report only evidence-based findings.
EOF
}

copy_repo() {
    local source_dir="$1"
    local target_dir="$2"

    mkdir -p "$target_dir"
    cp -R "$source_dir/." "$target_dir/"
}

run_validator() {
    local validator="$1"
    local repo_dir="$2"
    local output_file="$3"

    set +e
    bash "$validator" "$repo_dir" >"$output_file" 2>&1
    local status=$?
    set -e
    return "$status"
}

assert_wrapper_fails_with() {
    local repo_dir="$1"
    local expected="$2"
    local output_file

    output_file="$workspace/$(basename "$repo_dir").wrapper.output"

    if run_validator "$WRAPPER" "$repo_dir" "$output_file"; then
        sed -n '1,240p' "$output_file" >&2
        echo "compatibility wrapper unexpectedly accepted $repo_dir" >&2
        exit 1
    fi

    if ! grep -qF "$expected" "$output_file"; then
        sed -n '1,240p' "$output_file" >&2
        echo "compatibility wrapper failure did not include: $expected" >&2
        exit 1
    fi
}

valid_repo="$workspace/valid-independent-layers"
write_valid_repo "$valid_repo"
valid_output="$workspace/valid.wrapper.output"
if ! run_validator "$WRAPPER" "$valid_repo" "$valid_output"; then
    sed -n '1,240p' "$valid_output" >&2
    echo "compatibility wrapper rejected a valid canonical repository" >&2
    exit 1
fi
grep -qF 'Repository Type: org' "$valid_output"
grep -qF 'required instruction files exist' "$valid_output"
grep -qF 'AGENTS.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'copilot-instructions.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'AGENTS.md stays under runtime discovery size limit' "$valid_output"

missing_agents_repo="$workspace/missing-agents"
copy_repo "$valid_repo" "$missing_agents_repo"
rm "$missing_agents_repo/AGENTS.md"
assert_wrapper_fails_with "$missing_agents_repo" 'Missing: AGENTS.md'

missing_copilot_repo="$workspace/missing-copilot"
copy_repo "$valid_repo" "$missing_copilot_repo"
rm "$missing_copilot_repo/.github/copilot-instructions.md"
assert_wrapper_fails_with "$missing_copilot_repo" 'Missing: .github/copilot-instructions.md'

invalid_license_repo="$workspace/invalid-inline-license"
copy_repo "$valid_repo" "$invalid_license_repo"
sed -i 's/SPDX-License''-Identifier: CC0-1.0/SPDX-License''-Identifier: MIT/' \
    "$invalid_license_repo/.github/copilot-instructions.md"
assert_wrapper_fails_with "$invalid_license_repo" 'copilot-instructions.md has REUSE license'

malformed_markdown_repo="$workspace/malformed-markdown"
copy_repo "$valid_repo" "$malformed_markdown_repo"
printf '\n# Duplicate Top-Level Heading\n' \
    >>"$malformed_markdown_repo/.github/copilot-instructions.md"
assert_wrapper_fails_with "$malformed_markdown_repo" 'instruction Markdown passes lint'

oversized_repo="$workspace/oversized-agents"
copy_repo "$valid_repo" "$oversized_repo"
{
    printf '\n## Oversized Fixture\n\n'
    for _ in $(seq 1 700); do
        printf '%s\n' '- filler line that exceeds the runtime instruction discovery ceiling.'
    done
} >>"$oversized_repo/AGENTS.md"
assert_wrapper_fails_with "$oversized_repo" 'AGENTS.md stays under runtime discovery size limit'

# The compatibility filename must propagate exactly the canonical validator's
# result instead of implementing a weaker Copilot-only decision path.
wrapper_status=0
canonical_status=0
run_validator "$WRAPPER" "$invalid_license_repo" "$workspace/status.wrapper.output" \
    || wrapper_status=$?
run_validator "$CANONICAL_VALIDATOR" "$invalid_license_repo" "$workspace/status.canonical.output" \
    || canonical_status=$?
if [ "$wrapper_status" -ne "$canonical_status" ] || [ "$wrapper_status" -eq 0 ]; then
    echo "compatibility wrapper must propagate the canonical validator status" >&2
    exit 1
fi

printf 'validate-copilot-instructions tests passed\n'
