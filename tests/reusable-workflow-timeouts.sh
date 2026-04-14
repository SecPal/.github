#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

if [ ! -d ".github/workflows" ]; then
  echo "Expected directory '.github/workflows' was not found." >&2
  exit 1
fi

failures=()

while IFS= read -r workflow; do
  current_failures=()
  mapfile -t current_failures < <(
    awk -v path="$workflow" '
      BEGIN {
        in_jobs = 0
        jobs_indent = -1
        job_entry_indent = -1
        current_job = ""
        current_job_indent = -1
        current_has_timeout = 0
      }

      {
        line = $0
        if (line ~ /^[[:space:]]*$/) {
          indent = 0
        } else {
          indent = match(line, /[^[:space:]]/) - 1
        }
      }

      /^[[:space:]]*jobs:[[:space:]]*$/ {
        in_jobs = 1
        jobs_indent = indent
        job_entry_indent = -1
        current_job = ""
        current_job_indent = -1
        current_has_timeout = 0
        next
      }

      in_jobs && line !~ /^[[:space:]]*$/ && indent <= jobs_indent {
        if (current_job != "" && current_has_timeout == 0) {
          print path ":" current_job
        }
        in_jobs = 0
        next
      }

      in_jobs && line ~ /^[[:space:]]+[A-Za-z0-9_-]+:[[:space:]]*$/ && indent > jobs_indent {
        if (job_entry_indent == -1) {
          job_entry_indent = indent
        }
        if (indent != job_entry_indent) {
          next
        }

        if (current_job != "" && current_has_timeout == 0) {
          print path ":" current_job
        }

        current_job = line
        sub(/^[[:space:]]+/, "", current_job)
        sub(/:[[:space:]]*$/, "", current_job)
        current_job_indent = indent
        current_has_timeout = 0
        next
      }

      in_jobs && current_job != "" && line ~ /^[[:space:]]+timeout-minutes:[[:space:]]*/ && indent > current_job_indent {
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
  if [ ${#current_failures[@]} -gt 0 ]; then
    failures+=("${current_failures[@]}")
  fi
done < <(find .github/workflows -maxdepth 1 -type f -name 'reusable-*.yml' | sort)

if [ ${#failures[@]} -gt 0 ]; then
  echo "Missing timeout-minutes on reusable workflow jobs:" >&2
  for failure in "${failures[@]}"; do
    echo "  - $failure" >&2
  done
  exit 1
fi
