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

# Verify allowedLicenses is not empty (Bug fix from contracts: use length check)
if [ "$(jq -r '.allowedLicenses | length' .license-policy.json)" -eq 0 ]; then
  echo "Error: 'allowedLicenses' array is empty in .license-policy.json." >&2
  exit 1
fi

# Check for package.json
if [ ! -f package.json ]; then
  echo "Error: No package.json found in the current directory. Please run this script from the root of your Node.js project." >&2
  exit 1
fi

# Check for node_modules
if [ ! -d node_modules ]; then
  echo "Error: No node_modules directory found. Please run 'npm install' before checking licenses." >&2
  exit 1
fi

# Check if license-checker is installed
if [ ! -x node_modules/.bin/license-checker ]; then
  echo "Error: license-checker not found in node_modules/.bin/" >&2
  echo "Please install it: npm install --save-dev license-checker" >&2
  exit 1
fi

# Resolve absolute path for security (portable: readlink -f with fallback to pwd)
if command -v readlink >/dev/null 2>&1 && readlink -f node_modules/.bin/license-checker >/dev/null 2>&1; then
  LICENSE_CHECKER_BIN="$(readlink -f node_modules/.bin/license-checker)"
else
  # Fallback for systems without readlink -f (e.g., macOS)
  LICENSE_CHECKER_BIN="$(pwd)/node_modules/.bin/license-checker"
fi

# Run license-checker and handle errors (use local installation for security)
OUTPUT=$("$LICENSE_CHECKER_BIN" --production --onlyAllow "$ALLOWED" --summary 2>&1)
STATUS=$?
if [ $STATUS -ne 0 ]; then
  echo "Error: license-checker failed."
  echo "$OUTPUT"
  echo ""
  echo "Common reasons for failure:"
  echo "  - One or more dependencies have licenses not listed in allowedLicenses."
  echo "  - The project is misconfigured (e.g., missing package.json or node_modules)."
  echo "  - license-checker is not installed or not working as expected."
  exit $STATUS
fi

echo "$OUTPUT"
