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
  exit 1
fi

# Validate JSON and extract allowedLicenses
if ! jq -e '.allowedLicenses' .license-policy.json > /dev/null 2>&1; then
  echo "Error: .license-policy.json is missing or malformed, or 'allowedLicenses' key is absent." >&2
  exit 1
fi

ALLOWED=$(jq -r '.allowedLicenses | join(";")' .license-policy.json)

# Verify allowedLicenses is not empty
if [ -z "$ALLOWED" ]; then
  echo "Error: 'allowedLicenses' is empty in .license-policy.json." >&2
  exit 1
fi

npx license-checker --production --onlyAllow "$ALLOWED" --summary
