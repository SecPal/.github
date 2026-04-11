#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

failures=()

while IFS= read -r workflow; do
  while IFS= read -r failure; do
    failures+=("$failure")
  done < <(
    awk -v path="$workflow" '
      BEGIN {
        in_jobs = 0
        current_job = ""
        current_has_timeout = 0
      }

      /^jobs:$/ {
        in_jobs = 1
        next
      }

      in_jobs && /^[^[:space:]]/ {
        if (current_job != "" && current_has_timeout == 0) {
          print path ":" current_job
        }
        exit
      }

      in_jobs && /^  [A-Za-z0-9_-]+:$/ {
        if (current_job != "" && current_has_timeout == 0) {
          print path ":" current_job
        }

        current_job = $0
        sub(/^  /, "", current_job)
        sub(/:$/, "", current_job)
        current_has_timeout = 0
        next
      }

      in_jobs && current_job != "" && /^    timeout-minutes:/ {
        current_has_timeout = 1
        next
      }

      END {
        if (in_jobs && current_job != "" && current_has_timeout == 0) {
          print path ":" current_job
        }
      }
    ' "$workflow"
  )
done < <(find .github/workflows -maxdepth 1 -type f -name 'reusable-*.yml' | sort)

if [ ${#failures[@]} -gt 0 ]; then
  echo "Missing timeout-minutes on reusable workflow jobs:" >&2
  for failure in "${failures[@]}"; do
    echo "  - $failure" >&2
  done
  exit 1
fi
