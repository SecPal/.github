#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/.github"
cp "$REPO_ROOT/setup-hooks.sh" "$workspace/.github/setup-hooks.sh"

mkdir -p "$workspace/bin"
cat >"$workspace/bin/pre-commit" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$workspace/bin/pre-commit"

create_repo() {
  local repo="$1"

  mkdir -p "$workspace/$repo/scripts"

  cat >"$workspace/$repo/scripts/setup-pre-push.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  cat >"$workspace/$repo/scripts/setup-pre-commit.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  chmod +x "$workspace/$repo/scripts/setup-pre-push.sh" "$workspace/$repo/scripts/setup-pre-commit.sh"
}

for repo in api frontend contracts android secpal.app .github; do
  create_repo "$repo"
done

output_file="$workspace/output.txt"

if ! PATH="$workspace/bin:$PATH" bash "$workspace/.github/setup-hooks.sh" >"$output_file" 2>&1; then
  cat "$output_file"
  echo "setup-hooks.sh unexpectedly failed" >&2
  exit 1
fi

grep -q 'Successfully installed: 12 hooks' "$output_file"
grep -q 'All Git hooks have been successfully installed' "$output_file"
