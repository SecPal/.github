#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/review-governance-suite.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

real_python3="$(command -v python3)"
mkdir -p "$workspace/bin"
cat >"$workspace/bin/python3" <<EOF
#!/usr/bin/env bash
exec "$real_python3" "\$@"
EOF
chmod +x "$workspace/bin/python3"

for check in \
  "$SCRIPT_DIR"/validate-*-instructions.sh \
  "$SCRIPT_DIR"/*-review-memory*.sh; do
  test -x "$check"
  if [[ "$check" == "$SCRIPT_DIR/validate-ai-instructions.sh" ]]; then
    PATH="$workspace/bin:$PATH" "$check"
  else
    "$check"
  fi
done
