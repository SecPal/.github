#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e

# Check if .license-policy.json exists
if [ ! -f .license-policy.json ]; then
  echo "No .license-policy.json found, skipping license check."
  exit 0
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
  echo "Error: jq is required but not installed!" >&2
  echo "To install jq:" >&2
  echo "  - On Debian/Ubuntu: sudo apt install jq" >&2
  echo "  - On macOS (Homebrew): brew install jq" >&2
  echo "  - See https://stedolan.github.io/jq/download/ for other platforms." >&2
  exit 1
fi

# Validate JSON is well-formed
if ! jq empty .license-policy.json > /dev/null 2>&1; then
  echo "Error: .license-policy.json is malformed (invalid JSON)." >&2
  exit 1
fi

# Check for allowedLicenses key
if ! jq -e 'has("allowedLicenses") and (.allowedLicenses != null)' .license-policy.json > /dev/null 2>&1; then
  echo "Error: 'allowedLicenses' key is missing or null in .license-policy.json." >&2
  exit 1
fi

ALLOWED=$(jq -r '.allowedLicenses | join(";")' .license-policy.json)

# Verify allowedLicenses is not empty
if [ -z "$ALLOWED" ]; then
  echo "Error: 'allowedLicenses' is empty in .license-policy.json." >&2
  exit 1
fi

# Get package name and version from package.json to exclude it from the check
# (the root package itself should not be checked, only its dependencies)
if [ -f package.json ]; then
  PACKAGE_NAME=$(jq -r '.name // "unknown"' package.json)
  PACKAGE_VERSION=$(jq -r '.version // "0.0.0"' package.json)
  EXCLUDE_PACKAGE="${PACKAGE_NAME}@${PACKAGE_VERSION}"
else
  # No package.json means no root package to exclude
  EXCLUDE_PACKAGE=""
fi

# Exclude the root package from license checking (only check dependencies)
if [ -n "$EXCLUDE_PACKAGE" ]; then
  npx license-checker --production --onlyAllow "$ALLOWED" --excludePackages "$EXCLUDE_PACKAGE" --summary
else
  npx license-checker --production --onlyAllow "$ALLOWED" --summary
fi
