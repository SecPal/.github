<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# GitHub Review Thread Resolution Workflow

**Date:** 2025-10-17
**Context:** Lesson learned from PR #42 - automated thread resolution

## Problem

After addressing all Copilot review comments in PR #42, the Copilot Review Enforcement check kept failing with:

- ✅ Latest review: "generated no new comments"
- ❌ Check status: "9 unresolved threads"

**Root Cause:** Comments were addressed but threads were NOT marked as resolved via GitHub API.

## GitHub Thread Concepts

GitHub has TWO separate concepts:

### 1. Comment Body (Text)

- The actual text/content of a review comment
- Can be edited via REST API or MCP tools
- **Editing comment body ≠ Resolving thread**

### 2. Thread Resolved Status (Boolean Flag)

- A thread-level property (`isResolved: boolean`)
- Can ONLY be set via:
  - GitHub Web UI ("Resolve conversation" button)
  - GraphQL `resolveReviewThread` mutation
- **NOT available in MCP GitHub tools** (as of 2025-10-17)

## Failed Approaches

### ❌ Approach 1: Editing Comment Bodies

```bash
# This does NOT resolve the thread!
gh api -X PATCH /repos/SecPal/.github/pulls/comments/2438361851 \
  -f body="~~RESOLVED~~ Addressed in latest commits"
```

**Problem:** Changes comment text but `isResolved` remains `false`

### ❌ Approach 2: GraphQL Without Error Handling

```bash
# Silent failure - no output verification
gh api graphql -f query='
  mutation {
    resolveReviewThread(input: {threadId: "PRRC_..."}) {
      thread { id isResolved }
    }
  }
'
```

**Problem:** Command returned empty output, assumed success, but threads weren't resolved

## Correct Workflow

### Step 1: Get Thread IDs from Review Comments

```bash
gh api /repos/SecPal/.github/pulls/42/comments --jq '.[] | {
  id: .id,
  node_id: .node_id,
  path: .path,
  body: .body
}'
```

### Step 2: Resolve Each Thread via GraphQL (with error checking)

```bash
THREAD_ID="PRRC_kwDOQAoSms6RVnL7"

RESULT=$(gh api graphql -f query="
mutation {
  resolveReviewThread(input: {threadId: \"$THREAD_ID\"}) {
    thread {
      id
      isResolved
    }
  }
}
" 2>&1)

# Check for errors
if echo "$RESULT" | jq -e '.errors' > /dev/null 2>&1; then
  echo "❌ Failed to resolve thread $THREAD_ID"
  echo "$RESULT" | jq '.errors'
  exit 1
elif echo "$RESULT" | jq -e '.data.resolveReviewThread.thread.isResolved' > /dev/null 2>&1; then
  echo "✅ Thread $THREAD_ID resolved"
else
  echo "⚠️  Unexpected response: $RESULT"
  exit 1
fi
```

### Step 3: Verify All Threads Are Resolved

```bash
UNRESOLVED=$(gh api graphql -f query='
query {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: 42) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { path }
          }
        }
      }
    }
  }
}
' --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length')

if [ "$UNRESOLVED" -gt 0 ]; then
  echo "⚠️  Still $UNRESOLVED unresolved threads"
  echo "👉 Manual action required via GitHub UI"
  exit 1
else
  echo "✅ All threads resolved"
fi
```

### Step 4: Rerun Enforcement Check

```bash
# Only after ALL threads are resolved
gh run rerun $(gh run list --workflow="Copilot Review Enforcement" \
  --branch=docs/lessons-split --limit=1 --json databaseId --jq '.[0].databaseId')
```

## Complete Script Example

```bash
#!/bin/bash
set -euo pipefail

PR_NUMBER=42
REPO_OWNER="SecPal"
REPO_NAME=".github"

echo "🔍 Fetching unresolved threads for PR #$PR_NUMBER..."

# Get all unresolved thread IDs
THREAD_IDS=$(gh api graphql -f query="
query {
  repository(owner: \"$REPO_OWNER\", name: \"$REPO_NAME\") {
    pullRequest(number: $PR_NUMBER) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
        }
      }
    }
  }
}" --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | .[].id')

if [ -z "$THREAD_IDS" ]; then
  echo "✅ No unresolved threads found"
  exit 0
fi

echo "📋 Found unresolved threads:"
echo "$THREAD_IDS"

# Resolve each thread
for THREAD_ID in $THREAD_IDS; do
  echo "🔧 Resolving thread: $THREAD_ID"

  RESULT=$(gh api graphql -f query="
  mutation {
    resolveReviewThread(input: {threadId: \"$THREAD_ID\"}) {
      thread { id isResolved }
    }
  }
  " 2>&1)

  if echo "$RESULT" | jq -e '.errors' > /dev/null 2>&1; then
    echo "❌ Failed: $(echo "$RESULT" | jq -r '.errors[0].message')"
    echo "👉 Manual resolution required via GitHub UI"
    exit 1
  else
    echo "✅ Resolved"
  fi
done

echo "🎉 All threads resolved successfully!"
```

## Key Learnings

### 1. Always Verify GraphQL Results

```bash
# BAD: No verification
gh api graphql -f query='...'

# GOOD: Check for errors
RESULT=$(gh api graphql -f query='...' 2>&1)
if echo "$RESULT" | jq -e '.errors'; then
  # Handle error
fi
```

### 2. Empty Output ≠ Success

- Terminal output can be empty even on errors
- Always capture output and check JSON structure
- Use `2>&1` to capture stderr

### 3. MCP Tools Don't Cover Everything

- No `resolve_review_thread` MCP tool exists
- Must use raw GraphQL for thread resolution
- Document workarounds for future reference

### 4. Two-Step Process Required

1. **Fix the code** based on review comments
2. **Resolve the threads** to mark conversations complete

### 5. Fallback to Manual Resolution

If GraphQL fails:

- Don't try to bypass branch protection
- Inform user: "Please resolve threads manually via GitHub UI"
- Provide PR URL and wait for manual action

## Related Lessons

- Lesson #16: Review Comment Discipline
- Lesson #23: Review Workflow Discipline
- Lesson #21: Branch Protection Check Names Must Match Exactly

## Future Improvements

1. **Request MCP Tool:** Ask MCP maintainers to add `resolve_review_thread` tool
2. **Create Helper Script:** Package the complete script above as reusable workflow
3. **Pre-merge Checklist:** Always verify threads before requesting final review
