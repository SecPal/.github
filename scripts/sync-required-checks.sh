#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

REQUIRED_APPROVING_REVIEW_COUNT=0

REQUIRED_CONTEXTS_JSON="$(cat <<'EOF'
{
  ".github": [
    "Check REUSE Compliance",
    "Check License Compatibility",
    "Check Code Formatting",
    "Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "conflict-markers / Detect Git Conflict Markers",
    "Lint GitHub Actions Workflows",
    "CodeQL",
    "Validate PR Evidence",
    "Validate PR Title And Body Language",
    "Validate Signed PR Commits"
  ],
  "GuardGuide": [
    "check-conflicts / Detect Git Conflict Markers",
    "Check PR Size / Check PR Size",
    "Detect repository manifests",
    "AI Instructions / Validate AI Instructions",
    "Check REUSE Compliance / Check REUSE Compliance",
    "Detect JavaScript manifest",
    "Detect PHP manifest",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Vitest Tests / Build Project",
    "Laravel Pint / Check Code Style",
    "PHPStan / Static Analysis",
    "Pest Tests (PostgreSQL)",
    "Pest Tests (MariaDB)",
    "Analyze with CodeQL (javascript-typescript)"
  ],
  "android": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "check-conflicts / Detect Git Conflict Markers",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Vitest Tests",
    "Analyze with CodeQL (javascript-typescript)",
    "Check PR Size / Check PR Size",
    "AI Instructions / Validate AI Instructions",
    "Markdown Lint / Lint Markdown Files",
    "Certificate transparency"
  ],
  "api": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Laravel Pint / Check Code Style",
    "PHPStan / Static Analysis",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "PEST Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions"
  ],
  "guardguide.de": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "Astro TypeScript Check / Build Project",
    "Astro Build / Build Project",
    "Check PR Size / Check PR Size",
    "check-conflicts / Detect Git Conflict Markers",
    "Analyze Code (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "Node Tests / Run Tests"
  ],
  "contracts": [
    "REUSE Compliance / Check REUSE Compliance",
    "Prettier Formatting / Check Code Formatting",
    "OpenAPI Lint / Validate OpenAPI Specification",
    "Actionlint / Lint GitHub Actions Workflows",
    "pr-size / Check PR Size",
    "License Compatibility / Check License Compatibility",
    "Markdown Lint / Lint Markdown Files",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions"
  ],
  "frontend": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "ESLint / Run Linter",
    "TypeScript Check / Build Project",
    "Analyze with CodeQL (javascript-typescript)",
    "Markdown Lint / Lint Markdown Files",
    "Check PR Size / Check PR Size",
    "Vitest Tests",
    "check-conflicts / Detect Git Conflict Markers",
    "AI Instructions / Validate AI Instructions"
  ],
  "secpal.app": [
    "Check REUSE Compliance / Check REUSE Compliance",
    "Check License Compatibility / Check License Compatibility",
    "Formatting Check / Check Code Formatting",
    "Markdown Lint / Lint Markdown Files",
    "ESLint / Run Linter",
    "Astro TypeScript Check / Build Project",
    "Astro Build / Build Project",
    "Check PR Size / Check PR Size",
    "check-conflicts / Detect Git Conflict Markers",
    "Analyze Code (javascript-typescript)",
    "AI Instructions / Validate AI Instructions",
    "Node Tests / Run Tests"
  ]
}
EOF
)"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/sync-required-checks.sh --repo <name> --print-payload
  bash scripts/sync-required-checks.sh --repo <name> --print-review-payload
  bash scripts/sync-required-checks.sh [--repo <name>] --apply
  bash scripts/sync-required-checks.sh [--repo <name>] --apply-review-baseline

Options:
  --repo <name>            Restrict output or apply mode to a single repository.
  --print-payload          Print the required-check payload for one repository.
  --print-review-payload   Print the review-baseline payload for one repository.
  --apply                  Apply required checks via gh api.
  --apply-review-baseline  Apply the approval-count baseline via gh api.
  -h, --help               Show this help text.
EOF
}

known_repositories() {
  jq -r 'keys[]' <<<"$REQUIRED_CONTEXTS_JSON"
}

ensure_known_repository() {
  local repo="$1"

  if ! jq -e --arg repo "$repo" 'has($repo)' <<<"$REQUIRED_CONTEXTS_JSON" >/dev/null; then
    echo "Unknown repository: $repo" >&2
    echo "Known repositories:" >&2
    known_repositories | sed 's/^/  - /' >&2
    exit 2
  fi
}

build_payload() {
  local repo="$1"

  ensure_known_repository "$repo"

  jq -n \
    --arg repo "$repo" \
    --argjson config "$REQUIRED_CONTEXTS_JSON" \
    '{strict: false, checks: ($config[$repo] | map({context: ., app_id: -1}))}'
}

build_review_payload() {
  local repo="$1"

  ensure_known_repository "$repo"

  jq -n \
    --argjson count "$REQUIRED_APPROVING_REVIEW_COUNT" \
    '{required_approving_review_count: $count}'
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 2
  fi
}

apply_repository() {
  local repo="$1"

  ensure_known_repository "$repo"

  # Subshell scopes both the temp file and its EXIT trap so the payload is
  # always removed, even if build_payload or `gh api` fail under `set -e`.
  (
    payload_file="$(mktemp "${TMPDIR:-/tmp}/sync-required-checks.${repo//[^A-Za-z0-9]/_}.json.XXXXXX")"
    trap 'rm -f "$payload_file"' EXIT

    build_payload "$repo" > "$payload_file"

    if ! gh api "repos/SecPal/$repo/branches/main/protection/required_status_checks" \
      -X PATCH \
      --input "$payload_file" >/dev/null; then
      echo "Failed to update required_status_checks for SecPal/$repo." >&2
      echo "Hint: this PATCH endpoint only updates an existing branch protection rule; GitHub returns 404 if 'main' is not yet protected." >&2
      echo "      Initialize base branch protection first (see docs/ghas-setup.md), then rerun --apply." >&2
      exit 1
    fi
  )

  echo "Synced required checks for SecPal/$repo"
}

apply_review_repository() {
  local repo="$1"

  ensure_known_repository "$repo"

  (
    payload_file="$(mktemp "${TMPDIR:-/tmp}/sync-review-baseline.${repo//[^A-Za-z0-9]/_}.json.XXXXXX")"
    trap 'rm -f "$payload_file"' EXIT

    build_review_payload "$repo" > "$payload_file"

    if ! gh api "repos/SecPal/$repo/branches/main/protection/required_pull_request_reviews" \
      -X PATCH \
      --input "$payload_file" >/dev/null; then
      echo "Failed to update required_pull_request_reviews for SecPal/$repo." >&2
      exit 1
    fi
  )

  echo "Synced review baseline for SecPal/$repo"
}

repo=""
mode=""

set_mode() {
  local requested_mode="$1"

  if [[ -n "$mode" ]]; then
    echo "Multiple operation modes are not allowed: --$mode and --$requested_mode" >&2
    usage >&2
    exit 2
  fi

  mode="$requested_mode"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --repo" >&2
        usage >&2
        exit 2
      fi
      repo="$2"
      shift 2
      ;;
    --print-payload)
      set_mode "print-payload"
      shift
      ;;
    --print-review-payload)
      set_mode "print-review-payload"
      shift
      ;;
    --apply)
      set_mode "apply"
      shift
      ;;
    --apply-review-baseline)
      set_mode "apply-review-baseline"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$mode" ]]; then
  echo "Select a print or apply mode" >&2
  usage >&2
  exit 2
fi

require_command jq

if [[ "$mode" == "print-payload" ]]; then
  if [[ -z "$repo" ]]; then
    echo "--print-payload requires --repo <name>" >&2
    usage >&2
    exit 2
  fi

  build_payload "$repo"
  exit 0
fi

if [[ "$mode" == "print-review-payload" ]]; then
  if [[ -z "$repo" ]]; then
    echo "--print-review-payload requires --repo <name>" >&2
    usage >&2
    exit 2
  fi

  build_review_payload "$repo"
  exit 0
fi

require_command gh

if [[ -n "$repo" ]]; then
  if [[ "$mode" == "apply" ]]; then
    apply_repository "$repo"
  else
    apply_review_repository "$repo"
  fi
  exit 0
fi

while IFS= read -r configured_repo; do
  if [[ "$mode" == "apply" ]]; then
    apply_repository "$configured_repo"
  else
    apply_review_repository "$configured_repo"
  fi
done < <(known_repositories)
