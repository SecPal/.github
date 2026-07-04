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
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-license-compatibility.yml"
LOCAL_WORKFLOW="$REPO_ROOT/.github/workflows/license-compatibility.yml"
PREFLIGHT_SCRIPT="$REPO_ROOT/scripts/preflight.sh"
SECPAL_ATTRIBUTION_SHA256="0483f138e65753a0c8a3ba718d8ca9bdcba8633be8262c346d17c3a0b711b638"

failures=()

# ---------------------------------------------------------------------------
# Helper: extract the compatible_licenses array lines from the workflow YAML.
# Returns the raw YAML lines between the array open/close.
# ---------------------------------------------------------------------------
extract_allowlist() {
  local workflow="$1"
  awk '/compatible_licenses=\(/{found=1; next} found && /^[[:space:]]*\)[[:space:]]*$/{exit} found{print}' "$workflow"
}

# ---------------------------------------------------------------------------
# Helper: extract only quoted license identifiers from a workflow allowlist.
# ---------------------------------------------------------------------------
extract_allowlist_license_ids() {
  local workflow="$1"
  extract_allowlist "$workflow" \
    | sed 's/[[:space:]]*#.*$//' \
    | sed -nE 's/^[[:space:]]*"([^"]+)".*$/\1/p'
}

# ---------------------------------------------------------------------------
# positive_case LABEL LICENSE
#   Assert that LICENSE appears in the compatible_licenses array.
# ---------------------------------------------------------------------------
positive_case() {
  local label="$1"
  local license="$2"
  if ! extract_allowlist_license_ids "$REUSABLE_WORKFLOW" | grep -qxF "$license"; then
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
  if extract_allowlist_license_ids "$REUSABLE_WORKFLOW" | grep -qxF "$license"; then
    failures+=("FAIL [$label]: '$license' must NOT be in compatible_licenses but it was found")
  fi
}

# ---------------------------------------------------------------------------
# matching_allowlists_case LABEL
#   Assert that both workflow allowlist identifiers remain identical to avoid drift.
# ---------------------------------------------------------------------------
matching_allowlists_case() {
  local label="$1"
  local reusable_allowlist
  local local_allowlist

  reusable_allowlist="$(extract_allowlist_license_ids "$REUSABLE_WORKFLOW" | sort -u)"
  local_allowlist="$(extract_allowlist_license_ids "$LOCAL_WORKFLOW" | sort -u)"

  if [ "$reusable_allowlist" != "$local_allowlist" ]; then
    failures+=("FAIL [$label]: reusable and local workflow license identifiers diverged")
  fi
}

# ---------------------------------------------------------------------------
# preflight_guidance_case LABEL
#   Assert that preflight remediation names the full allowlist drift scope.
# ---------------------------------------------------------------------------
preflight_guidance_case() {
  local label="$1"
  local expected_guidance="Restore missing approved license entries, keep the local and reusable allowlists aligned, or fix the incompatible-license checks in .github/workflows/reusable-license-compatibility.yml and .github/workflows/license-compatibility.yml before continuing."

  if ! grep -qF "$expected_guidance" "$PREFLIGHT_SCRIPT"; then
    failures+=("FAIL [$label]: preflight guidance does not describe both workflow allowlists and alignment")
  fi
}

# ---------------------------------------------------------------------------
# secpal_attribution_guard_case LABEL
#   Assert that the workflow validates the SecPal attribution addendum content
#   and requires AGPL in every file that uses the license reference.
# ---------------------------------------------------------------------------
secpal_attribution_guard_case() {
  local label="$1"
  local workflow_name
  local workflow_path

  for workflow_name in reusable local; do
    if [ "$workflow_name" = "reusable" ]; then
      workflow_path="$REUSABLE_WORKFLOW"
    else
      workflow_path="$LOCAL_WORKFLOW"
    fi

    if ! grep -qF "$SECPAL_ATTRIBUTION_SHA256" "$workflow_path"; then
      failures+=("FAIL [$label]: $workflow_name workflow does not pin the approved SecPal attribution addendum hash")
    fi

    if ! grep -qF 'LICENSES/LicenseRef-SecPal-Attribution.txt' "$workflow_path"; then
      failures+=("FAIL [$label]: $workflow_name workflow does not require the SecPal attribution license file")
    fi

    if ! grep -qF 'must use the approved SecPal attribution addendum text' "$workflow_path"; then
      failures+=("FAIL [$label]: $workflow_name workflow does not reject mismatched SecPal attribution text")
    fi

    if ! grep -qF 'is only allowed with AGPL-3.0-or-later in the same file' "$workflow_path"; then
      failures+=("FAIL [$label]: $workflow_name workflow does not require AGPL alongside the SecPal attribution license reference")
    fi
  done
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
positive_case "LicenseRef-SecPal-Attribution accepted" "LicenseRef-SecPal-Attribution"

# ODbL-1.0 must be in the allowlist (OpenPLZ geo-data and similar datasets).
positive_case "ODbL-1.0 accepted for data files" "ODbL-1.0"

# Incompatible / copyleft-only licenses must never appear in the allowlist.
negative_case "GPL-2.0-only rejected"  "GPL-2.0-only"
negative_case "GPL-2.0-or-later rejected" "GPL-2.0-or-later"
negative_case "SSPL-1.0 rejected"      "SSPL-1.0"
negative_case "BUSL-1.1 rejected"      "BUSL-1.1"
negative_case "proprietary rejected"   "LicenseRef-Proprietary"
matching_allowlists_case "reusable and local workflow allowlists aligned"
preflight_guidance_case "preflight guidance covers allowlist alignment"
secpal_attribution_guard_case "SecPal attribution guard covers file content and AGPL pairing"

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

echo "✓ license-compatibility allowlist regression tests passed ($(extract_allowlist_license_ids "$REUSABLE_WORKFLOW" | awk 'END{print NR}') entries checked)"
