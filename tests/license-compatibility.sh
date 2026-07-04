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
TAILWIND_PLUS_SHA256="f34dfb2ffa166cb60cf0aa4b9cedca33ab8caee1438ef81e14399e24bdadac3c"

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
# custom_license_ref_guard_case LABEL
#   Assert that both workflow files validate approved custom license text and
#   reject SPDX expressions that are missing AGPL or use OR-pairing.
# ---------------------------------------------------------------------------
custom_license_ref_guard_case() {
  local label="$1"
  local workflow
  local workflow_path
  local workflow_label

  for workflow_path in "$REUSABLE_WORKFLOW" "$LOCAL_WORKFLOW"; do
    workflow="$(cat "$workflow_path")"
    workflow_label="$(basename "$workflow_path")"

    if ! printf '%s' "$workflow" | grep -qF "$SECPAL_ATTRIBUTION_SHA256"; then
      failures+=("FAIL [$label]: $workflow_label does not pin the approved SecPal attribution addendum hash")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'LICENSES/LicenseRef-SecPal-Attribution.txt'; then
      failures+=("FAIL [$label]: $workflow_label does not require the SecPal attribution license file")
    fi

    if ! printf '%s' "$workflow" | grep -qF "$TAILWIND_PLUS_SHA256"; then
      failures+=("FAIL [$label]: $workflow_label does not pin the approved Tailwind Plus license text hash")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'LICENSES/LicenseRef-TailwindPlus.txt'; then
      failures+=("FAIL [$label]: $workflow_label does not require the Tailwind Plus license file")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'must use the approved $reference_label text'; then
      failures+=("FAIL [$label]: $workflow_label does not reject mismatched SecPal attribution text")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'reference_label="$5"'; then
      failures+=("FAIL [$label]: $workflow_label does not reject mismatched Tailwind Plus text")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'must appear in a tracked SPDX-License-Identifier expression'; then
      failures+=("FAIL [$label]: $workflow_label does not require tracked SPDX expressions for custom license references")
    fi

    if ! printf '%s' "$workflow" | grep -qF 'is only allowed with $required_license' \
      || ! printf '%s' "$workflow" | grep -qF 'in the same SPDX-License-Identifier expression:'; then
      failures+=("FAIL [$label]: $workflow_label does not reject OR-paired or non-AGPL custom license expressions")
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
custom_license_ref_guard_case "custom license reference guards cover both workflow files"

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
