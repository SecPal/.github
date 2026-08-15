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
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
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
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
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
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    local repo_type="${3:-org}"

    (
        cd "$repo_dir"
        REPO_TYPE="$repo_type" bash "$VALIDATOR"
    ) >"$output_file" 2>&1
}

assert_passes() {
    local repo_dir="$1"
    local output_file="$2"
    local repo_type="${3:-org}"

    if ! run_validator "$repo_dir" "$output_file" "$repo_type"; then
        sed -n '1,240p' "$output_file" >&2
        echo "validator unexpectedly rejected $repo_dir" >&2
        exit 1
    fi
}

assert_fails_with() {
    local repo_dir="$1"
    local expected="$2"
    local repo_type="${3:-org}"
    local output_file
    local exit_code

    output_file="$workspace/$(basename "$repo_dir").output"

    set +e
    run_validator "$repo_dir" "$output_file" "$repo_type"
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
grep -qF 'instruction paths stay inside the repository' "$valid_output"
grep -qF 'AGENTS.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'copilot-instructions.md is readable UTF-8 Markdown' "$valid_output"
grep -qF 'AGENTS.md has REUSE license' "$valid_output"
grep -qF 'instruction Markdown passes lint' "$valid_output"
grep -qF 'instruction overlays include valid frontmatter' "$valid_output"
grep -qF 'AGENTS.md stays under runtime discovery size limit' "$valid_output"

obsolete_agents_license_repo="$workspace/obsolete-agents-license"
copy_valid_repo "$valid_repo" "$obsolete_agents_license_repo"
sed -i \
    's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution/' \
    "$obsolete_agents_license_repo/AGENTS.md"
assert_fails_with "$obsolete_agents_license_repo" 'AGENTS.md has REUSE license'

obsolete_copilot_license_repo="$workspace/obsolete-copilot-license"
copy_valid_repo "$valid_repo" "$obsolete_copilot_license_repo"
sed -i \
    's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution/' \
    "$obsolete_copilot_license_repo/.github/copilot-instructions.md"
assert_fails_with "$obsolete_copilot_license_repo" \
    'copilot-instructions.md has REUSE license'

obsolete_inline_with_valid_sidecar_repo="$workspace/obsolete-inline-with-valid-sidecar"
copy_valid_repo "$valid_repo" "$obsolete_inline_with_valid_sidecar_repo"
printf '%s\n' \
    'SPDX-FileCopyrightText: 2026 SecPal Contributors' \
    'SPDX-License''-Identifier: AGPL-3.0-or-later' \
    >"$obsolete_inline_with_valid_sidecar_repo/.github/copilot-instructions.md.license"
sed -i \
    's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution/' \
    "$obsolete_inline_with_valid_sidecar_repo/.github/copilot-instructions.md"
assert_fails_with "$obsolete_inline_with_valid_sidecar_repo" \
    'copilot-instructions.md has REUSE license'

obsolete_overlay_license_repo="$workspace/obsolete-overlay-license"
copy_valid_repo "$valid_repo" "$obsolete_overlay_license_repo"
sed -i \
    's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution/' \
    "$obsolete_overlay_license_repo/.github/instructions/example.instructions.md"
assert_fails_with "$obsolete_overlay_license_repo" \
    '.github/instructions/example.instructions.md has REUSE license'

duplicate_agents_license_repo="$workspace/duplicate-agents-license"
copy_valid_repo "$valid_repo" "$duplicate_agents_license_repo"
sed -i \
    '/SPDX-License''-Identifier: AGPL-3.0-or-later/aSPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution' \
    "$duplicate_agents_license_repo/AGENTS.md"
assert_fails_with "$duplicate_agents_license_repo" 'AGENTS.md has REUSE license'

late_duplicate_agents_license_repo="$workspace/late-duplicate-agents-license"
copy_valid_repo "$valid_repo" "$late_duplicate_agents_license_repo"
printf '%s\n' \
    '<!-- SPDX-License''-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution -->' \
    >>"$late_duplicate_agents_license_repo/AGENTS.md"
assert_fails_with "$late_duplicate_agents_license_repo" \
    'AGENTS.md has REUSE license'

api_license_repo="$workspace/allowed-api-cc0"
copy_valid_repo "$valid_repo" "$api_license_repo"
printf '{"name":"secpal/api"}\n' >"$api_license_repo/composer.json"
sed -i 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: CC0-1.0/' \
    "$api_license_repo/AGENTS.md" \
    "$api_license_repo/.github/copilot-instructions.md"
assert_passes "$api_license_repo" "$workspace/allowed-api-cc0.output" api

legacy_frontend_license_repo="$workspace/rejected-legacy-frontend-cc0"
copy_valid_repo "$valid_repo" "$legacy_frontend_license_repo"
sed -i 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: CC0-1.0/' \
    "$legacy_frontend_license_repo/AGENTS.md" \
    "$legacy_frontend_license_repo/.github/copilot-instructions.md"
assert_fails_with "$legacy_frontend_license_repo" \
    'AGENTS.md must declare exactly one complete permitted SPDX expression: AGPL-3.0-or-later' \
    frontend

wrong_org_root_license_repo="$workspace/wrong-org-root-license"
copy_valid_repo "$valid_repo" "$wrong_org_root_license_repo"
sed -i 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: MIT/' \
    "$wrong_org_root_license_repo/AGENTS.md"
assert_fails_with "$wrong_org_root_license_repo" \
    'AGENTS.md must declare exactly one complete permitted SPDX expression: AGPL-3.0-or-later'

wrong_api_root_license_repo="$workspace/wrong-api-root-license"
copy_valid_repo "$valid_repo" "$wrong_api_root_license_repo"
printf '{"name":"secpal/api"}\n' \
    >"$wrong_api_root_license_repo/composer.json"
wrong_api_root_output="$workspace/wrong-api-root-license.output"
set +e
(
    cd "$wrong_api_root_license_repo"
    SECPAL_REPOSITORY_NAME=api bash "$VALIDATOR"
) >"$wrong_api_root_output" 2>&1
wrong_api_root_status=$?
set -e
if [ "$wrong_api_root_status" -eq 0 ]; then
    sed -n '1,240p' "$wrong_api_root_output" >&2
    echo "trusted API identity must require the CC0 baseline" >&2
    exit 1
fi
grep -qF \
    'AGENTS.md must declare exactly one complete permitted SPDX expression: CC0-1.0' \
    "$wrong_api_root_output"

for allowed_license in CC0-1.0 MIT Apache-2.0; do
    allowed_license_slug="${allowed_license//./-}"
    allowed_license_repo="$workspace/allowed-$allowed_license_slug"
    allowed_license_output="$workspace/allowed-$allowed_license_slug.output"
    copy_valid_repo "$valid_repo" "$allowed_license_repo"
    sed -i \
        "s/SPDX-License""-Identifier: AGPL-3.0-or-later/SPDX-License""-Identifier: $allowed_license/" \
        "$allowed_license_repo/.github/instructions/example.instructions.md"
    assert_passes "$allowed_license_repo" "$allowed_license_output"
done

html_comment_repo="$workspace/html-comment-license"
copy_valid_repo "$valid_repo" "$html_comment_repo"
html_license_identifier='SPDX-License'"-Identifier: AGPL-3.0-or-later"
printf -v html_header_sed \
    '1,4c<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors -->\\\n<!-- %s -->' \
    "$html_license_identifier"
sed -i "$html_header_sed" \
    "$html_comment_repo/AGENTS.md" \
    "$html_comment_repo/.github/copilot-instructions.md"
assert_passes "$html_comment_repo" "$workspace/html-comment-license.output"

unrelated_custom_license_repo="$workspace/unrelated-custom-license"
copy_valid_repo "$valid_repo" "$unrelated_custom_license_repo"
mkdir -p "$unrelated_custom_license_repo/vendor"
printf '%s\n' \
    'SPDX-FileCopyrightText: 2026 Example Vendor' \
    'SPDX-License''-Identifier: LicenseRef-Example-''Vendor' \
    >"$unrelated_custom_license_repo/vendor/example.txt.license"
assert_passes "$unrelated_custom_license_repo" \
    "$workspace/unrelated-custom-license.output"

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

detected_api_repo="$workspace/detected-api"
copy_valid_repo "$valid_repo" "$detected_api_repo"
printf '{"name":"secpal/api"}\n' >"$detected_api_repo/composer.json"
sed -i 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: CC0-1.0/' \
    "$detected_api_repo/AGENTS.md" \
    "$detected_api_repo/.github/copilot-instructions.md"
detected_api_output="$workspace/detected-api.output"
(
    cd "$detected_api_repo"
    SECPAL_REPOSITORY_NAME=api bash "$VALIDATOR"
) >"$detected_api_output" 2>&1
grep -qF 'Repository Type: api' "$detected_api_output"

ambient_github_api_output="$workspace/ambient-github-api.output"
GITHUB_REPOSITORY=SecPal/.github \
    bash "$VALIDATOR" "$detected_api_repo" >"$ambient_github_api_output" 2>&1
grep -qF 'Repository Type: api' "$ambient_github_api_output"
grep -qF 'All tests passed' "$ambient_github_api_output"

api_named_guardguide_repo="$workspace/api-path-heuristic/GuardGuide"
copy_valid_repo "$detected_api_repo" "$api_named_guardguide_repo"
api_named_guardguide_output="$workspace/api-named-guardguide.output"
bash "$VALIDATOR" "$api_named_guardguide_repo" \
    >"$api_named_guardguide_output" 2>&1
grep -qF 'Repository Type: api' "$api_named_guardguide_output"
grep -qF 'All tests passed' "$api_named_guardguide_output"

untrusted_api_manifest_repo="$workspace/untrusted-api-manifest"
copy_valid_repo "$valid_repo" "$untrusted_api_manifest_repo"
printf '{"name":"secpal/api"}\n' >"$untrusted_api_manifest_repo/composer.json"
sed -i 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: CC0-1.0/' \
    "$untrusted_api_manifest_repo/AGENTS.md" \
    "$untrusted_api_manifest_repo/.github/copilot-instructions.md"
untrusted_api_manifest_output="$workspace/untrusted-api-manifest.output"
bash "$VALIDATOR" "$untrusted_api_manifest_repo" \
    >"$untrusted_api_manifest_output" 2>&1
grep -qF 'Repository Type: api' "$untrusted_api_manifest_output"
grep -qF 'All tests passed' "$untrusted_api_manifest_output"

frontend_with_composer_repo="$workspace/frontend-with-composer"
copy_valid_repo "$valid_repo" "$frontend_with_composer_repo"
printf '{"name":"secpal/api"}\n' \
    >"$frontend_with_composer_repo/composer.json"
printf '{"name":"secpal/frontend","devDependencies":{"vite":"latest"}}\n' \
    >"$frontend_with_composer_repo/package.json"
frontend_with_composer_output="$workspace/frontend-with-composer.output"
(
    cd "$frontend_with_composer_repo"
    GITHUB_REPOSITORY=SecPal/frontend bash "$VALIDATOR"
) >"$frontend_with_composer_output" 2>&1
grep -qF 'Repository Type: frontend' "$frontend_with_composer_output"
grep -qF 'All tests passed' "$frontend_with_composer_output"

non_api_override_repo="$workspace/non-api-override"
copy_valid_repo "$valid_repo" "$non_api_override_repo"
printf '{"name":"example/vite-plugin","extra":{"name":"secpal/api"}}\n' \
    >"$non_api_override_repo/composer.json"
printf '{"name":"secpal/frontend","devDependencies":{"vite":"latest"}}\n' \
    >"$non_api_override_repo/package.json"
non_api_override_output="$workspace/non-api-override.output"
(
    cd "$non_api_override_repo"
    REPO_TYPE=api bash "$VALIDATOR"
) >"$non_api_override_output" 2>&1
grep -qF 'Repository Type: frontend' "$non_api_override_output"
grep -qF 'All tests passed' "$non_api_override_output"

detected_guardguide_repo="$workspace/detected-guardguide"
copy_valid_repo "$valid_repo" "$detected_guardguide_repo"
printf '{"name":"secpal/guardguide"}\n' \
    >"$detected_guardguide_repo/composer.json"
detected_guardguide_output="$workspace/detected-guardguide.output"
bash "$VALIDATOR" "$detected_guardguide_repo" \
    >"$detected_guardguide_output" 2>&1
grep -qF 'Repository Type: guardguide' "$detected_guardguide_output"

detected_website_repo="$workspace/detected-guardguide-website"
copy_valid_repo "$valid_repo" "$detected_website_repo"
printf '{"name":"secpal/guardguide.de"}\n' \
    >"$detected_website_repo/package.json"
printf 'export default {};\n' >"$detected_website_repo/astro.config.mjs"
detected_website_output="$workspace/detected-guardguide-website.output"
bash "$VALIDATOR" "$detected_website_repo" \
    >"$detected_website_output" 2>&1
grep -qF 'Repository Type: website' "$detected_website_output"

symlinked_agents_repo="$workspace/symlinked-agents"
symlinked_agents_target="$workspace/external-AGENTS.md"
copy_valid_repo "$valid_repo" "$symlinked_agents_repo"
mv "$symlinked_agents_repo/AGENTS.md" "$symlinked_agents_target"
ln -s "$symlinked_agents_target" "$symlinked_agents_repo/AGENTS.md"
assert_fails_with "$symlinked_agents_repo" \
    'instruction paths stay inside the repository'

symlinked_github_repo="$workspace/symlinked-github-directory"
symlinked_github_target="$workspace/external-github-directory"
copy_valid_repo "$valid_repo" "$symlinked_github_repo"
mv "$symlinked_github_repo/.github" "$symlinked_github_target"
ln -s "$symlinked_github_target" "$symlinked_github_repo/.github"
assert_fails_with "$symlinked_github_repo" \
    'instruction paths stay inside the repository'

symlinked_copilot_repo="$workspace/symlinked-copilot"
symlinked_copilot_target="$workspace/external-copilot-instructions.md"
copy_valid_repo "$valid_repo" "$symlinked_copilot_repo"
mv "$symlinked_copilot_repo/.github/copilot-instructions.md" \
    "$symlinked_copilot_target"
ln -s "$symlinked_copilot_target" \
    "$symlinked_copilot_repo/.github/copilot-instructions.md"
assert_fails_with "$symlinked_copilot_repo" \
    'instruction paths stay inside the repository'

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
    'copilot-instructions.md must declare exactly one complete permitted SPDX expression: AGPL-3.0-or-later'

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

missing_overlay_license_repo="$workspace/missing-overlay-license"
copy_valid_repo "$valid_repo" "$missing_overlay_license_repo"
sed -i '/SPDX-License''-Identifier:/d' \
    "$missing_overlay_license_repo/.github/instructions/example.instructions.md"
assert_fails_with "$missing_overlay_license_repo" \
    '.github/instructions/example.instructions.md has REUSE license'

empty_frontmatter_name_repo="$workspace/empty-frontmatter-name"
copy_valid_repo "$valid_repo" "$empty_frontmatter_name_repo"
sed -i 's/^name:.*/name: ""/' \
    "$empty_frontmatter_name_repo/.github/instructions/example.instructions.md"
assert_fails_with "$empty_frontmatter_name_repo" \
    'instruction overlays include valid frontmatter'

null_frontmatter_apply_to_repo="$workspace/null-frontmatter-apply-to"
copy_valid_repo "$valid_repo" "$null_frontmatter_apply_to_repo"
sed -i 's/^applyTo:.*/applyTo: # no path scope/' \
    "$null_frontmatter_apply_to_repo/.github/instructions/example.instructions.md"
assert_fails_with "$null_frontmatter_apply_to_repo" \
    'instruction overlays include valid frontmatter'

invalid_yaml_frontmatter_repo="$workspace/invalid-yaml-frontmatter"
copy_valid_repo "$valid_repo" "$invalid_yaml_frontmatter_repo"
sed -i 's/^applyTo:.*/applyTo: [/' \
    "$invalid_yaml_frontmatter_repo/.github/instructions/example.instructions.md"
assert_fails_with "$invalid_yaml_frontmatter_repo" \
    'instruction overlays include valid frontmatter'

symlinked_frontmatter_repo="$workspace/symlinked-frontmatter"
symlinked_frontmatter_target="$workspace/external.instructions.md"
copy_valid_repo "$valid_repo" "$symlinked_frontmatter_repo"
cat >"$symlinked_frontmatter_target" <<'EOF'
---
name: ""
applyTo: [
---

# External Instructions
EOF
rm "$symlinked_frontmatter_repo/.github/instructions/example.instructions.md"
ln -s "$symlinked_frontmatter_target" \
    "$symlinked_frontmatter_repo/.github/instructions/example.instructions.md"
assert_fails_with "$symlinked_frontmatter_repo" \
    'instruction paths stay inside the repository'

symlinked_overlay_dir_repo="$workspace/symlinked-overlay-directory"
symlinked_overlay_dir_target="$workspace/external-instruction-directory"
copy_valid_repo "$valid_repo" "$symlinked_overlay_dir_repo"
mkdir -p "$symlinked_overlay_dir_target"
mv "$symlinked_overlay_dir_repo/.github/instructions/example.instructions.md" \
    "$symlinked_overlay_dir_target/example.instructions.md"
rmdir "$symlinked_overlay_dir_repo/.github/instructions"
ln -s "$symlinked_overlay_dir_target" \
    "$symlinked_overlay_dir_repo/.github/instructions"
assert_fails_with "$symlinked_overlay_dir_repo" \
    'instruction paths stay inside the repository'

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

# The pinned js-yaml 5 package exposes its CommonJS entry point through
# package.json instead of a root index.js. Exercise that installed layout in an
# isolated validator toolchain so the validator must use Node's package
# resolution rather than assume a package entry-point filename.
installed_yaml_root="$workspace/js-yaml-5-toolchain"
installed_yaml_validator="$installed_yaml_root/scripts/validate-ai-instructions.sh"
installed_yaml_repo="$installed_yaml_root/repository"
mkdir -p "$installed_yaml_root/scripts" "$installed_yaml_root/node_modules"
cp "$VALIDATOR" "$installed_yaml_validator"
cp -R "$REPO_ROOT/node_modules/js-yaml" "$installed_yaml_root/node_modules/js-yaml"
cp -R "$REPO_ROOT/node_modules/argparse" "$installed_yaml_root/node_modules/argparse"
copy_valid_repo "$valid_repo" "$installed_yaml_repo"

if [ -e "$installed_yaml_root/node_modules/js-yaml/index.js" ]; then
    echo "js-yaml 5 regression fixture must not contain a root index.js" >&2
    exit 1
fi

installed_yaml_output="$workspace/js-yaml-5-toolchain.output"
if ! (
    cd "$installed_yaml_repo"
    PATH="$REPO_ROOT/node_modules/.bin:$PATH" \
        REPO_TYPE=org bash "$installed_yaml_validator"
) >"$installed_yaml_output" 2>&1; then
    sed -n '1,240p' "$installed_yaml_output" >&2
    echo "validator must load the installed js-yaml 5 package layout" >&2
    exit 1
fi
grep -qF 'instruction overlays include valid frontmatter' "$installed_yaml_output"

# Focused frontmatter must fail closed when the repository-pinned YAML parser
# is unavailable, even if Markdownlint itself is available globally.
isolated_yaml_root="$workspace/no-frontmatter-yaml-toolchain"
isolated_yaml_validator="$isolated_yaml_root/scripts/validate-ai-instructions.sh"
isolated_yaml_bin="$isolated_yaml_root/bin"
isolated_yaml_repo="$isolated_yaml_root/repository"
mkdir -p "$isolated_yaml_root/scripts" "$isolated_yaml_bin"
cp "$VALIDATOR" "$isolated_yaml_validator"
copy_valid_repo "$valid_repo" "$isolated_yaml_repo"
for required_tool in bash dirname grep head find python3 wc node; do
    ln -s "$(command -v "$required_tool")" "$isolated_yaml_bin/$required_tool"
done

missing_yaml_output="$workspace/missing-frontmatter-yaml.output"
set +e
(
    cd "$isolated_yaml_repo"
    PATH="$isolated_yaml_bin:$REPO_ROOT/node_modules/.bin" \
        REPO_TYPE=org /bin/bash "$isolated_yaml_validator"
) >"$missing_yaml_output" 2>&1
missing_yaml_status=$?
set -e

if [ "$missing_yaml_status" -eq 0 ]; then
    sed -n '1,240p' "$missing_yaml_output" >&2
    echo "validator must fail when the frontmatter YAML parser is unavailable" >&2
    exit 1
fi
grep -qF 'repository-pinned js-yaml is unavailable' "$missing_yaml_output"

isolated_yaml_no_overlays_repo="$isolated_yaml_root/repository-without-overlays"
copy_valid_repo "$valid_repo" "$isolated_yaml_no_overlays_repo"
rm -r "$isolated_yaml_no_overlays_repo/.github/instructions"
isolated_yaml_no_overlays_output="$workspace/missing-frontmatter-yaml-no-overlays.output"
if ! (
    cd "$isolated_yaml_no_overlays_repo"
    PATH="$isolated_yaml_bin:$REPO_ROOT/node_modules/.bin" \
        REPO_TYPE=org /bin/bash "$isolated_yaml_validator"
) >"$isolated_yaml_no_overlays_output" 2>&1; then
    sed -n '1,240p' "$isolated_yaml_no_overlays_output" >&2
    echo "validator must not require a frontmatter parser without focused overlays" >&2
    exit 1
fi
grep -qF 'Skipped (no focused instruction files present)' \
    "$isolated_yaml_no_overlays_output"

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
for required_tool in bash dirname grep head find python3 wc; do
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
