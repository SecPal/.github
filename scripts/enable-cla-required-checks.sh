#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

repos=(
  "SecPal/.github"
  "SecPal/api"
  "SecPal/frontend"
  "SecPal/contracts"
  "SecPal/android"
  "SecPal/secpal.app"
)

for repo in "${repos[@]}"; do
  echo "==> ${repo}"

  if ! gh api "repos/${repo}/contents/.github/workflows/license-cla.yml?ref=main" >/dev/null 2>&1; then
    echo "  skip: .github/workflows/license-cla.yml is not on main yet"
    continue
  fi

  protection_json="$(mktemp)"
  payload_json="$(mktemp)"
  trap 'rm -f "$protection_json" "$payload_json"' RETURN

  gh api "repos/${repo}/branches/main/protection" >"$protection_json"

  jq '
    {
      strict: .required_status_checks.strict,
      checks: (
        .required_status_checks.checks
        + if any(.required_status_checks.checks[]?; .context == "license/cla")
          then []
          else [{context: "license/cla", app_id: null}]
          end
      )
    }
  ' "$protection_json" >"$payload_json"

  gh api -X PATCH "repos/${repo}/branches/main/protection/required_status_checks" --input "$payload_json" >/dev/null
  echo "  ok: ensured required status check license/cla"

  rm -f "$protection_json" "$payload_json"
  trap - RETURN
done
