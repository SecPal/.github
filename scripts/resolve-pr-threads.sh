#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

#
# resolve-pr-threads.sh - Automated PR Thread Resolution
#
# Purpose: Resolve all unresolved review threads for a given PR
# Usage: ./resolve-pr-threads.sh <PR_NUMBER> [REPO_OWNER] [REPO_NAME]
#
# IMPORTANT: This script should be executed directly, not sourced.
# The cleanup traps are configured for direct execution only.
#
# Prerequisites:
#   - gh CLI installed and authenticated
#   - jq installed for JSON processing
#
# Exit codes:
#   0 - Success (all threads resolved)
#   1 - Error (validation failed, API error, or unresolved threads remain)
#

# Configuration
# Try to detect from git remote, fallback to defaults
# Extract owner and repo from git remote URL (supports SSH and HTTPS)
GIT_URL=$(git remote get-url origin 2>/dev/null || echo "")
# SSH: git@host:owner/repo.git OR git@host:port:owner/repo.git
if [[ "$GIT_URL" =~ ^git@([^:]+)(:[0-9]+)?:([^/]+)/([^/]+)\.git$ ]]; then
  DEFAULT_OWNER="${BASH_REMATCH[3]}"
  DEFAULT_REPO="${BASH_REMATCH[4]}"
# HTTPS: https://host/owner/repo.git OR https://host/owner/repo (with optional query/anchor)
elif [[ "$GIT_URL" =~ ^https?://[^/]+/([^/]+)/([^/?#]+)(\.git)?([?#].*)?$ ]]; then
  DEFAULT_OWNER="${BASH_REMATCH[1]}"
  # Strip .git suffix if present
  DEFAULT_REPO="${BASH_REMATCH[2]%.git}"
else
  DEFAULT_OWNER="SecPal"
  DEFAULT_REPO=".github"
fi

REPO_OWNER="${2:-$DEFAULT_OWNER}"
REPO_NAME="${3:-$DEFAULT_REPO}"
PR_NUMBER="${1:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
usage() {
  cat << EOF
Usage: $0 <PR_NUMBER> [REPO_OWNER] [REPO_NAME]

Resolve all unresolved review threads for a GitHub Pull Request.

Arguments:
  PR_NUMBER     Pull Request number (required)
  REPO_OWNER    Repository owner (default: SecPal)
  REPO_NAME     Repository name (default: .github)

Examples:
  $0 58                           # Resolve threads for PR #58 in SecPal/.github
  $0 42 SecPal contracts          # Resolve threads for PR #42 in SecPal/contracts
  $0 15 myorg myrepo              # Resolve threads for PR #15 in myorg/myrepo

Prerequisites:
  - gh CLI must be installed and authenticated
  - jq must be installed

Exit codes:
  0 - All threads successfully resolved
  1 - Error occurred (validation, API, or unresolved threads)
EOF
}

log_info() {
  echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
  echo -e "${GREEN}✅${NC} $*"
}

log_warning() {
  echo -e "${YELLOW}⚠️${NC} $*"
}

log_error() {
  echo -e "${RED}❌${NC} $*"
}

validate_prerequisites() {
  local missing=0

  if ! command -v gh &> /dev/null; then
    log_error "gh CLI is not installed. Install from: https://cli.github.com/"
    missing=1
  fi

  if ! command -v jq &> /dev/null; then
    log_error "jq is not installed. Install from: https://stedolan.github.io/jq/"
    missing=1
  fi

  if [ $missing -eq 1 ]; then
    return 1
  fi

  # Check gh authentication
  if ! gh auth status &> /dev/null; then
    log_error "gh CLI is not authenticated. Run: gh auth login"
    return 1
  fi

  return 0
}

get_unresolved_threads() {
  local pr_number=$1
  local owner=$2
  local repo=$3

  log_info "Fetching unresolved threads for PR #$pr_number in $owner/$repo..."

  local all_thread_ids=""
  local has_next_page=true
  local cursor=""

  while [ "$has_next_page" = true ]; do
    local query='
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              body
              path
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}'

    local result
    if [ -z "$cursor" ]; then
      result=$(gh api graphql \
        -f query="$query" \
        -f owner="$owner" \
        -f name="$repo" \
        -F number="$pr_number" 2>&1)
    else
      result=$(gh api graphql \
        -f query="$query" \
        -f owner="$owner" \
        -f name="$repo" \
        -F number="$pr_number" \
        -f cursor="$cursor" 2>&1)
    fi

    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
      log_error "Failed to fetch threads from GraphQL API"
      echo "$result" >&2
      return 1
    fi

    # Check for GraphQL errors
    if echo "$result" | jq -e '.errors' > /dev/null 2>&1; then
      log_error "GraphQL query returned errors:"
      echo "$result" | jq -r '.errors[] | "  - \(.message)"' >&2
      return 1
    fi

    # Extract unresolved thread IDs from this page
    local page_thread_ids
    page_thread_ids=$(echo "$result" | jq -r '
      .data.repository.pullRequest.reviewThreads.nodes[]
      | select(.isResolved == false)
      | .id
    ')

    if [ -n "$page_thread_ids" ]; then
      if [ -z "$all_thread_ids" ]; then
        all_thread_ids="$page_thread_ids"
      else
        all_thread_ids="$all_thread_ids"$'\n'"$page_thread_ids"
      fi
    fi

    # Check if there are more pages
    has_next_page=$(echo "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
    cursor=$(echo "$result" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')

    if [ "$has_next_page" != "true" ]; then
      break
    fi
  done

  if [ -z "$all_thread_ids" ]; then
    log_success "No unresolved threads found"
    return 0
  fi

  echo "$all_thread_ids"
}

resolve_thread() {
  local thread_id=$1

  log_info "Resolving thread: $thread_id"

  local mutation='
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      id
      isResolved
    }
  }
}'

  # Create temporary file for output
  local tmpfile
  tmpfile=$(umask 077; mktemp)
  trap 'rm -f -- "$tmpfile"' EXIT INT TERM

  # Execute mutation and capture output
  gh api graphql \
    -f query="$mutation" \
    -f threadId="$thread_id" > "$tmpfile" 2>&1

  local exit_code=$?

  # Check gh exit code
  if [ $exit_code -ne 0 ]; then
    log_error "gh api command failed for thread $thread_id"
    cat "$tmpfile" >&2
    rm -f -- "$tmpfile"
    return 1
  fi

  # Check for GraphQL errors
  if jq -e '.errors' "$tmpfile" > /dev/null 2>&1; then
    log_error "Failed to resolve thread $thread_id"
    jq -r '.errors[] | "  - \(.message)"' "$tmpfile" >&2
    rm -f -- "$tmpfile"
    return 1
  fi

  # Verify thread was actually resolved
  if ! jq -er '.data.resolveReviewThread.thread.isResolved == true' "$tmpfile" > /dev/null 2>&1; then
    log_error "Thread $thread_id was not marked as resolved"
    cat "$tmpfile" >&2
    rm -f -- "$tmpfile"
    return 1
  fi

  rm -f -- "$tmpfile"
  log_success "Thread resolved: $thread_id"
  return 0
}

verify_all_resolved() {
  local pr_number=$1
  local owner=$2
  local repo=$3

  log_info "Verifying all threads are resolved..."

  local query='
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
        }
      }
    }
  }
}'

  local result
  result=$(gh api graphql \
    -f query="$query" \
    -f owner="$owner" \
    -f name="$repo" \
    -F number="$pr_number" 2>&1)

  local exit_code=$?

  if [ $exit_code -ne 0 ]; then
    log_error "Failed to verify thread resolution"
    echo "$result" >&2
    return 1
  fi

  local unresolved_count
  unresolved_count=$(echo "$result" | jq -r '
    .data.repository.pullRequest.reviewThreads.nodes
    | map(select(.isResolved == false))
    | length
  ')

  if [ "$unresolved_count" -gt 0 ]; then
    log_error "Still $unresolved_count unresolved threads remaining"
    return 1
  fi

  log_success "All threads verified as resolved"
  return 0
}

main() {
  # Show usage if no arguments or help flag
  if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
    exit 0
  fi

  # Validate PR number
  if [ -z "$PR_NUMBER" ]; then
    log_error "PR_NUMBER is required"
    echo ""
    usage
    exit 1
  fi

  # Validate PR number is numeric
  if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
    log_error "PR_NUMBER must be a number, got: $PR_NUMBER"
    exit 1
  fi

  log_info "Starting thread resolution for PR #$PR_NUMBER in $REPO_OWNER/$REPO_NAME"
  echo ""

  # Validate prerequisites
  if ! validate_prerequisites; then
    exit 1
  fi

  # Get unresolved threads
  local thread_ids
  thread_ids=$(get_unresolved_threads "$PR_NUMBER" "$REPO_OWNER" "$REPO_NAME")
  local get_status=$?

  if [ $get_status -ne 0 ]; then
    exit 1
  fi

  # If no threads to resolve, we're done
  if [ -z "$thread_ids" ]; then
    log_success "All threads already resolved!"
    exit 0
  fi

  # Count threads
  local thread_count
  thread_count=$(echo "$thread_ids" | wc -l | tr -d ' ')
  log_info "Found $thread_count unresolved thread(s)"
  echo ""

  # Resolve each thread
  local failed=0
  while IFS= read -r thread_id; do
    if ! resolve_thread "$thread_id"; then
      failed=1
    fi
  done <<< "$thread_ids"

  echo ""

  # Check if any resolutions failed
  if [ $failed -ne 0 ]; then
    log_error "Some threads failed to resolve"
    exit 1
  fi

  # Verify all threads are resolved
  if ! verify_all_resolved "$PR_NUMBER" "$REPO_OWNER" "$REPO_NAME"; then
    log_error "Verification failed - manual action required"
    exit 1
  fi

  echo ""
  log_success "🎉 All $thread_count thread(s) successfully resolved!"
  log_info "You can now request a Copilot review for PR #$PR_NUMBER"

  exit 0
}

# Run main function
main "$@"
