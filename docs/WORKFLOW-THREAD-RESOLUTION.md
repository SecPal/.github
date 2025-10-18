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

## Key Concepts: Node ID Types

**CRITICAL:** GitHub has different node ID formats for different objects:

- `PRRC_*` = **Pull Request Review Comment** (individual comment)
- `PRRT_*` = **Pull Request Review Thread** (conversation/thread)

**The `resolveReviewThread` GraphQL mutation requires `PRRT_*` thread IDs, NOT `PRRC_*` comment IDs!**

Using comment IDs (`PRRC_*`) will fail with: `Could not resolve to PullRequestReviewThread node with the global id`

## Correct Workflow

### Step 1: Get Thread IDs via GraphQL (NOT REST API)

```bash
PR_NUMBER=42

# Get review threads with their IDs and first comment
gh api graphql -f query='
query($number: Int!) {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
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
      }
    }
  }
}' -f number=$PR_NUMBER --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | {
  thread_id: .id,
  path: .comments.nodes[0].path,
  preview: .comments.nodes[0].body[:100]
}'
```

**Output Example:**

```json
{
  "thread_id": "PRRT_kwDOQAoSms5eewML",
  "path": "scripts/validate.sh",
  "preview": "Consider adding error handling..."
}
```

### Step 2: Resolve Each Thread via GraphQL (with error checking)

```bash
THREAD_ID="PRRT_kwDOQAoSms5eewML"  # Note: PRRT_* not PRRC_*

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

# Check for errors (repeated pattern for self-contained copy-paste examples)
# Note: This error-checking pattern appears in Step 2 and the Complete Script.
# We intentionally keep it duplicated so each section is independently usable.
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
PR_NUMBER=42
UNRESOLVED=$(gh api graphql -f query='
query($number: Int!) {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
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
' -f number=$PR_NUMBER --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length')

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
# Get the FAILED enforcement run (the one blocking merge)
FAILED_RUN=$(gh run list --workflow="Copilot Review Enforcement" \
  --branch=$(git branch --show-current) --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "failure") | .databaseId' | head -1)

if [ -n "$FAILED_RUN" ]; then
  echo "🔄 Rerunning failed check: $FAILED_RUN"
  gh run rerun $FAILED_RUN
else
  echo "✅ No failed runs found"
fi
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
THREAD_IDS=$(gh api graphql -f query='
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
        }
      }
    }
  }
}' -f owner="$REPO_OWNER" -f name="$REPO_NAME" -f number=$PR_NUMBER \
  --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | .[].id')

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

# Verify all threads are resolved
UNRESOLVED=$(gh api graphql -f query='
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
        nodes { id isResolved }
      }
    }
  }
}' -f owner="$REPO_OWNER" -f name="$REPO_NAME" -f number=$PR_NUMBER \
  --jq '.data.repository.pullRequest.reviewThreads.nodes | map(select(.isResolved == false)) | length')

if [ "$UNRESOLVED" -gt 0 ]; then
  echo "⚠️  Still $UNRESOLVED unresolved - manual action required"
  exit 1
fi

# Rerun the FAILED enforcement check (not the latest one!)
FAILED_RUN=$(gh run list --workflow="Copilot Review Enforcement" \
  --branch=$(git branch --show-current) --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "failure") | .databaseId' | head -1)

if [ -n "$FAILED_RUN" ]; then
  echo "🔄 Rerunning failed enforcement check: $FAILED_RUN"
  gh run rerun $FAILED_RUN
  echo "✅ Check rerun requested - PR should be ready to merge in ~30s"
else
  echo "✅ No failed runs - PR is ready to merge"
fi
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

### 6. Rerun the FAILED Check, Not the Latest

**CRITICAL:** When rerunning enforcement checks:

```bash
# WRONG: Reruns the latest (might be SUCCESS already)
gh run rerun $(gh run list --limit=1 --json databaseId --jq '.[0].databaseId')

# CORRECT: Rerun the FAILED check (the one blocking merge)
FAILED_RUN=$(gh run list --workflow="Copilot Review Enforcement" \
  --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "failure") | .databaseId' | head -1)
gh run rerun $FAILED_RUN
```

GitHub shows ALL check runs, but only the **failed** one blocks the merge.
Rerunning the latest (successful) check does nothing to unblock.

---

## Optimized Workflow (Recommended)

**Standard workflow (PR #42-56):**

```
1. Fix code addressing review comments
2. Commit + Push
3. Request Copilot review
4. Wait for review (90s delay + processing)
5. Review has "no new comments"
6. Resolve threads via GraphQL
7. Rerun enforcement check
8. Merge
```

**Optimized workflow (PR #57+):**

```
1. Fix code addressing review comments
2. Commit + Push
3. Resolve addressed threads immediately (GraphQL)
4. Request Copilot review
5. Review sees "no unresolved threads" → Can approve immediately
6. Merge (no rerun needed)
```

**Why better?**

- Threads already resolved when review runs
- Copilot sees clean state → Direct approval possible
- Saves 1-2 review cycles
- No need to rerun failed checks

**Implementation:**

```bash
# After pushing fixes
git push

# Immediately resolve threads for comments you addressed
PR_NUMBER=57
gh api graphql -f query='
query($number: Int!) {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { body path }
          }
        }
      }
    }
  }
}' -f number=$PR_NUMBER | jq -r '.data.repository.pullRequest.reviewThreads.nodes[] |
  select(.isResolved == false) |
  .id' | while IFS= read -r THREAD_ID; do
    gh api graphql -f query="
    mutation {
      resolveReviewThread(input: {threadId: \"$THREAD_ID\"}) {
        thread { id isResolved }
      }
    }" > /dev/null && echo "✅ Resolved $THREAD_ID"
done

# NOW request review (subsequent push)
# Use MCP tool (preferred) or API with JSON array syntax
# gh api POST /repos/SecPal/.github/pulls/57/requested_reviewers \
#   -f team_reviewers='["copilot"]'
```

**When to use:**

- ✅ You've addressed ALL comments from previous review
- ✅ You're confident fixes are correct
- ❌ Still have open questions/discussion
- ❌ Partial fixes (some comments not yet addressed)

---

## Related Lessons

- Lesson #16: Review Comment Discipline
- Lesson #23: Review Workflow Discipline (updated with optimized workflow)
- Lesson #21: Branch Protection Check Names Must Match Exactly

## Future Improvements

1. **Request MCP Tool:** Ask MCP maintainers to add `resolve_review_thread` tool
2. **Create Helper Script:** Package the complete script above as reusable workflow
3. **Pre-merge Checklist:** Always verify threads before requesting final review

---

**Last Updated:** 2025-10-18
**Changes:** Added `PRRT_*` vs `PRRC_*` explanation, optimized workflow (resolve → request)
