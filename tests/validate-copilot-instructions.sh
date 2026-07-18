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

legacy_repo="$workspace/legacy-only"
mkdir -p "$legacy_repo/.github/instructions"
cat >"$legacy_repo/.markdownlint.json" <<'EOF'
{
  "MD013": false
}
EOF
cat >"$legacy_repo/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Legacy Copilot Instructions

These instructions are self-contained for this repository at runtime.
Do not automatically inherit from sibling repositories.
The literal `@extends` token is ordinary Markdown, not a validation contract.
EOF

PATH="$workspace/bin:$PATH" bash "$REPO_ROOT/scripts/validate-copilot-instructions.sh" "$legacy_repo"

broken_legacy_repo="$workspace/broken-legacy"
mkdir -p "$broken_legacy_repo/.github/instructions"
cp "$legacy_repo/.markdownlint.json" "$broken_legacy_repo/.markdownlint.json"
cat >"$broken_legacy_repo/.github/copilot-instructions.md" <<'EOF'
# Broken Legacy Copilot Instructions
EOF

set +e
broken_output="$(PATH="$workspace/bin:$PATH" bash "$REPO_ROOT/scripts/validate-copilot-instructions.sh" "$broken_legacy_repo" 2>&1)"
broken_status=$?
set -e

if [ "$broken_status" -eq 0 ]; then
    echo "legacy validator unexpectedly passed without SPDX header" >&2
    exit 1
fi

if [[ "$broken_output" != *"Missing SPDX header"* ]]; then
    echo "legacy validator must report missing SPDX headers" >&2
    echo "$broken_output" >&2
    exit 1
fi
