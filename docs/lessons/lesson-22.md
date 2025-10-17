<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #22 (Reusable Workflow Bootstrap Paradox & GraphQL Fix)

**Category:** Advanced Workflows
**Priority:** HIGH
**Status:** ✅ Implemented
**Date:** 2025-10-15
**Repository:** .github

## Problem

**Two combined issues:**

1. **GraphQL vs REST API Mismatch:**
   - Threads resolved via UI (GraphQL `resolveReviewThread`)
   - Workflow uses REST API → still sees comments as "unresolved"
   - APIs NOT synchronized!

2. **Bootstrap Paradox:**
   - Fix is on branch
   - Workflow calls `@main` (doesn't have fix yet)
   - Can't merge because workflow fails
   - Can't fix workflow because can't merge
   - **Infinite loop!**

## Solution

**Part 1: Use GraphQL for Thread Resolution**

```bash
# NEW (GraphQL) - CORRECT
unresolved=$(gh api graphql -f query='{
  repository(owner: "'$OWNER'", name: "'$REPO'") {
    pullRequest(number: '$PR') {
      reviewThreads(first: 100) {
        nodes { isResolved }
      }
    }
  }
}' --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length')
```

**Part 2: Break Bootstrap Paradox**
Use GraphQL mutation to resolve threads directly:

```bash
# Resolve thread via API
gh api graphql -f query='mutation {
  resolveReviewThread(input: {threadId: "'$THREAD_ID'"}) {
    thread { id isResolved }
  }
}'
```

## Action for Future Repos

1. **Always use GraphQL** for review thread operations (not REST)
2. For bootstrap paradoxes: Resolve threads via API, rerun check
3. Consider `@main` vs `@sha` trade-off for reusable workflows
4. Document GraphQL queries in workflow comments

## Related Lessons

- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md)
- [Lesson #19 (Infinite Loop Prevention)](lesson-19.md)
- [Lesson #20 (Workflow Approval)](lesson-20.md) - Rerun technique

---

**Last Updated:** 2025-10-17
