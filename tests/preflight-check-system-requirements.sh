#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PREFLIGHT_SCRIPT="$REPO_ROOT/scripts/preflight.sh"

if [ ! -f "$PREFLIGHT_SCRIPT" ]; then
  echo "Missing preflight script: $PREFLIGHT_SCRIPT" >&2
  exit 1
fi

if ! grep -Fq 'tests/check-system-requirements.sh' "$PREFLIGHT_SCRIPT"; then
  echo "scripts/preflight.sh must invoke tests/check-system-requirements.sh so Android requirements regressions run in enforced validation." >&2
  exit 1
fi

echo "tests/preflight-check-system-requirements.sh: preflight wiring verified."
