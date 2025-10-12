#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e

if [ ! -f .license-policy.json ]; then
  echo "No .license-policy.json found, skipping license check."
  exit 0
fi

ALLOWED=$(jq -r '.allowedLicenses | join(";")' .license-policy.json)
npx license-checker --production --onlyAllow "$ALLOWED" --summary
