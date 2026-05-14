#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression tests for the reusable license-compatibility allowlist.
# Verifies the allowlist accepts explicitly-approved identifiers and
# rejects clearly-incompatible ones so future edits cannot silently
# widen or narrow the policy without preflight catching the change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/reusable-license-compatibility.yml"

failures=()

# ---------------------------------------------------------------------------
# Helper: extract the compatible_licenses array lines from the workflow YAML.
# Returns the raw YAML lines between the array open/close.
# ---------------------------------------------------------------------------
extract_allowlist() {
  awk '/compatible_licenses=\(/{found=1; next} found && /^[[:space:]]*\)[[:space:]]*$/{exit} found{print}' "$WORKFLOW"
}

# ---------------------------------------------------------------------------
# positive_case LABEL LICENSE
#   Assert that LICENSE appears in the compatible_licenses array.
# ---------------------------------------------------------------------------
positive_case() {
  local label="$1"
  local license="$2"
  if ! extract_allowlist | grep -qF "\"$license\""; then
    failures+=("FAIL [$label]: expected '$license' to be in compatible_licenses but it was not found")
  fi
}

# ---------------------------------------------------------------------------
# negative_case LABEL LICENSE
#   Assert that LICENSE does NOT appear in the compatible_licenses array.
# ---------------------------------------------------------------------------
negative_case() {
  local label="$1"
  local license="$2"
  if extract_allowlist | grep -qF "\"$license\""; then
    failures+=("FAIL [$label]: '$license' must NOT be in compatible_licenses but it was found")
  fi
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Core AGPL-family / permissive licenses must stay in the allowlist.
positive_case "core AGPL license accepted"        "AGPL-3.0-or-later"
positive_case "CC0-1.0 accepted"                  "CC0-1.0"
positive_case "MIT accepted"                      "MIT"
positive_case "Apache-2.0 accepted"               "Apache-2.0"
positive_case "OFL-1.1 accepted"                  "OFL-1.1"
positive_case "LicenseRef-TailwindPlus accepted"  "LicenseRef-TailwindPlus"

# ODbL-1.0 must be in the allowlist (OpenPLZ geo-data and similar datasets).
positive_case "ODbL-1.0 accepted for data files" "ODbL-1.0"

# Incompatible / copyleft-only licenses must never appear in the allowlist.
negative_case "GPL-2.0-only rejected"  "GPL-2.0-only"
negative_case "GPL-2.0-or-later rejected" "GPL-2.0-or-later"
negative_case "SSPL-1.0 rejected"      "SSPL-1.0"
negative_case "BUSL-1.1 rejected"      "BUSL-1.1"
negative_case "proprietary rejected"   "LicenseRef-Proprietary"

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

if [ ${#failures[@]} -gt 0 ]; then
  echo "❌ license-compatibility allowlist regression failures:" >&2
  for f in "${failures[@]}"; do
    echo "  $f" >&2
  done
  exit 1
fi

echo "✓ license-compatibility allowlist regression tests passed ($(extract_allowlist | grep -c '"' || true) entries checked)"
