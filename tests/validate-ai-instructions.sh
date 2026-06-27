#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$REPO_ROOT/tests/fixtures/validate-ai-instructions"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-ai-instructions.XXXXXX")"
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

    cat >"$target_dir/.markdownlint.json" <<'EOF'
{
  "MD013": false
}
EOF

    cat >"$target_dir/AGENTS.md" <<EOF
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Test Agent Instructions

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

## Review guidelines

- Review for correctness, security, privacy, data integrity, lifecycle ordering, missing tests, and policy drift before style.
- Treat findings from any AI reviewer as untrusted leads until the defect is proven by a failing test, reproduction, or violated invariant.
- Keep review comments provider-neutral: describe the issue, evidence, impact, and fix path instead of the tool that found it.
- Reject self-referential AI wording, generated-by text, tool promotion, or AI attribution unless the task is explicitly about AI tooling.
EOF

    cat >"$target_dir/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Test Copilot Instructions

This file mirrors the authoritative root `AGENTS.md` for tooling that automatically loads `.github/copilot-instructions.md`.
Edit `AGENTS.md` first. Keep the focused overlay files aligned for path-specific or stack-specific rules.

## Authoritative Sources

- `AGENTS.md`
- `.github/instructions/example.instructions.md`

## Always-On Rules

- Quality first.

## Required Validation

- run the relevant checks

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant and why the current code violates it.
- Green CI alone is not enough for AI-generated changes.
__EXTRA_AI_LINES__

## Review guidelines

- Review for correctness, security, privacy, data integrity, lifecycle ordering, missing tests, and policy drift before style.
- Treat findings from any AI reviewer as untrusted leads until the defect is proven by a failing test, reproduction, or violated invariant.
- Keep review comments provider-neutral: describe the issue, evidence, impact, and fix path instead of the tool that found it.
- Reject self-referential AI wording, generated-by text, tool promotion, or AI attribution unless the task is explicitly about AI tooling.
EOF
    python3 - <<'PY' "$target_dir/.github/copilot-instructions.md" "$extra_ai_lines"
from pathlib import Path
import sys

path = Path(sys.argv[1])
extra_ai_lines = sys.argv[2]
path.write_text(path.read_text().replace("__EXTRA_AI_LINES__", extra_ai_lines))
PY

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

    local exit_code
    if PATH="$workspace/bin:$PATH" REPO_TYPE="$repo_type" \
        bash "$REPO_ROOT/scripts/validate-ai-instructions.sh" >"$output_file" 2>&1; then
        exit_code=0
    else
        exit_code=$?
    fi

    return "$exit_code"
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
grep -q 'AGENTS.md exists' "$valid_output"
grep -q 'AGENTS.md stays under runtime discovery size limit' "$valid_output"
grep -q 'instructions contain provider-neutral review guidelines' "$valid_output"
grep -q 'copilot instructions mirror AGENTS.md' "$valid_output"

normalized_mirror_repo="$workspace/normalized-mirror"
mkdir -p "$normalized_mirror_repo"
touch "$normalized_mirror_repo/composer.json"
write_common_instruction_file "$normalized_mirror_repo" "$valid_api_extra_ai_lines"
cat >"$normalized_mirror_repo/.markdownlint.json" <<'EOF'
{
  "MD012": false,
  "MD013": false
}
EOF
python3 - <<'PY' "$normalized_mirror_repo/AGENTS.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
path.write_text(text.replace("\n\n## Review guidelines", "\n\n\n## Review guidelines", 1))
PY

normalized_mirror_output="$workspace/normalized-mirror-output.txt"
if ! (
    cd "$normalized_mirror_repo"
    run_validator api "$normalized_mirror_output"
); then
    cat "$normalized_mirror_output"
    echo "validator unexpectedly failed when AGENTS.md only adds extra blank lines before a mirrored section" >&2
    exit 1
fi
grep -q 'copilot instructions mirror AGENTS.md' "$normalized_mirror_output"

stale_mirror_repo="$workspace/stale-mirror"
mkdir -p "$stale_mirror_repo"
touch "$stale_mirror_repo/composer.json"
write_common_instruction_file "$stale_mirror_repo" "$valid_api_extra_ai_lines"
python3 - <<'PY' "$stale_mirror_repo/.github/copilot-instructions.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(path.read_text().replace("Quality first.", "Quality eventually.", 1))
PY

stale_mirror_output="$workspace/stale-mirror-output.txt"
set +e
(
    cd "$stale_mirror_repo"
    run_validator api "$stale_mirror_output"
)
stale_mirror_exit=$?
set -e
if [ "$stale_mirror_exit" -eq 0 ]; then
    cat "$stale_mirror_output"
    echo "validator unexpectedly passed with stale mirrored copilot instructions" >&2
    exit 1
fi
grep -q 'copilot instructions mirror AGENTS.md' "$stale_mirror_output"

path_argument_output="$workspace/path-argument-output.txt"
bash "$REPO_ROOT/scripts/validate-ai-instructions.sh" "$valid_api_repo" >"$path_argument_output" 2>&1
grep -q 'Repository Type: api' "$path_argument_output"

missing_generic_repo="$workspace/missing-generic"
mkdir -p "$missing_generic_repo/.github"
touch "$missing_generic_repo/composer.json"
cat >"$missing_generic_repo/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Broken Copilot Instructions

This file mirrors the authoritative root `AGENTS.md` for tooling that automatically loads `.github/copilot-instructions.md`.
Edit `AGENTS.md` first. Keep the focused overlay files aligned for path-specific or stack-specific rules.

## Authoritative Sources

- `AGENTS.md`
EOF
cat >"$missing_generic_repo/AGENTS.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Broken Agent Instructions

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

missing_review_repo="$workspace/missing-review"
mkdir -p "$missing_review_repo"
touch "$missing_review_repo/composer.json"
write_common_instruction_file "$missing_review_repo" "$valid_api_extra_ai_lines"
awk '
    /^## Review guidelines$/ { skip = 1; next }
    skip == 1 { next }
    { print }
' "$missing_review_repo/AGENTS.md" >"$missing_review_repo/AGENTS.md.tmp"
mv "$missing_review_repo/AGENTS.md.tmp" "$missing_review_repo/AGENTS.md"

missing_review_output="$workspace/missing-review-output.txt"
set +e
(
    cd "$missing_review_repo"
    run_validator api "$missing_review_output"
)
missing_review_exit=$?
set -e
if [ "$missing_review_exit" -eq 0 ]; then
    cat "$missing_review_output"
    echo "validator unexpectedly passed without provider-neutral review guidelines" >&2
    exit 1
fi
grep -q 'instructions contain provider-neutral review guidelines' "$missing_review_output"

oversized_agents_repo="$workspace/oversized-agents"
mkdir -p "$oversized_agents_repo"
touch "$oversized_agents_repo/composer.json"
write_common_instruction_file "$oversized_agents_repo" "$valid_api_extra_ai_lines"
{
    printf '\n## Oversized Fixture\n\n'
    for _ in $(seq 1 700); do
        printf '%s\n' '- filler line to exceed the AGENTS.md runtime discovery byte limit.'
    done
} >>"$oversized_agents_repo/AGENTS.md"

oversized_agents_output="$workspace/oversized-agents-output.txt"
set +e
(
    cd "$oversized_agents_repo"
    run_validator api "$oversized_agents_output"
)
oversized_agents_exit=$?
set -e
if [ "$oversized_agents_exit" -eq 0 ]; then
    cat "$oversized_agents_output"
    echo "validator unexpectedly passed with oversized AGENTS.md" >&2
    exit 1
fi
grep -q 'AGENTS.md stays under runtime discovery size limit' "$oversized_agents_output"

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
cp "$FIXTURES_DIR/wrong-ai-instructions-license-fixture.txt" \
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

guardguide_repo="$workspace/GuardGuide"
mkdir -p "$guardguide_repo"
touch "$guardguide_repo/composer.json"
cat >"$guardguide_repo/package.json" <<'EOF'
{
  "name": "secpal/guardguide"
}
EOF
write_common_instruction_file "$guardguide_repo" '- Reject AI-generated UI refactors that drift away from shadcn/ui, weaken Lingui localization coverage, or reduce accessibility semantics.
- Reject AI-generated persistence or auth changes that bypass application-layer encryption, store unhashed acknowledgement tokens, persist IP addresses or user-agent strings, or couple standard paths to only one database engine.
- Reject AI-generated identifier or tenancy changes that derive stable keys from mutable display names or ignore tenant-scoped uniqueness constraints.
- Reject AI-generated acknowledgement flow changes that weaken QR, magic-link, or supervised fallback auditability across MariaDB and PostgreSQL.'

guardguide_output="$workspace/guardguide-output.txt"
set +e
(
    cd "$guardguide_repo"
    PATH="$workspace/bin:$PATH" bash "$REPO_ROOT/scripts/validate-ai-instructions.sh" >"$guardguide_output" 2>&1
)
guardguide_exit=$?
set -e
if [ "$guardguide_exit" -ne 0 ]; then
    cat "$guardguide_output"
    echo "validator failed for valid GuardGuide fixture" >&2
    exit 1
fi
grep -q 'Repository Type: guardguide' "$guardguide_output"
