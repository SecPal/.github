<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #23 (Review Workflow Discipline)

**Category:** Recent Additions
**Priority:** HIGH
**Status:** 🚧 In Progress
**Date:** 2025-10-16
**Repository:** .github

## Problem

After implementing Copilot Review enforcement (Lesson #18), discovered gaps in review workflow discipline through PRs #34-36:

**Issues Discovered:**

1. **Variable interpolation in GraphQL** (PR #34) - Security risk, needed immediate fix
2. **MCP tool standardization** (PR #35) - Inconsistent patterns across tools
3. **Thread resolution loop** (PR #36) - Robust error handling missing

**Root Cause:**
TODOs from PR #32 code review identified issues but weren't systematically tracked → took 4 PRs to complete all fixes.

## Solution

**Established Review Workflow Discipline:**

1. **Track ALL review TODOs** systematically
2. **One TODO = One PR** (focused, reviewable changes)
3. **Sequential execution** (don't mix concerns)
4. **Request Copilot review via MCP after each push:**
   ```bash
   # Ask GitHub Copilot in chat (MCP tool available via Claude Desktop/Cline)
   # Example uses concrete values for clarity - customize for your repo/PR:
   # mcp_github_github_request_copilot_review('<owner>', '<repo>', <pr_number>)
   mcp_github_github_request_copilot_review('SecPal', '.github', 42)
   ```
5. **Address ALL comments** - fix code based on feedback
6. **Resolve ALL threads via GraphQL** (CRITICAL - see [Thread Resolution Workflow](../WORKFLOW-THREAD-RESOLUTION.md))
7. **Verify threads resolved** before merge
8. **Check enforcement passes** before merge

**Complete Review Workflow (PR #58+ Standard):**

```
1. First push → Copilot reviews automatically ✅ (wait 90 seconds)
2. Address comments → Fix code, commit, push
3. Resolve threads → Via GraphQL BEFORE requesting review
4. Request review → Use MCP tool (manual request required after subsequent pushes)
5. Wait for review → Check if "no new comments"
6. All green → Merge ✅
```

**Why resolve threads BEFORE requesting review?**

- ✅ Threads already resolved when Copilot runs → Can approve immediately
- ✅ Saves 1-2 review cycles (no "unresolved threads" comment)
- ✅ No need to rerun failed checks
- ✅ Cleaner review state → Better review quality

**Thread Resolution Timing:**

- ✅ **After push, BEFORE request** - PRIMARY approach (PR #58+)
- ⚠️ **After review completes** - Old workflow (requires rerun, wastes cycles)
- ❌ **Before addressing code** - Premature (comments not fixed yet)

**CRITICAL:** Resolving threads is REQUIRED - addressing comments in code is NOT enough!

**Automation Available:** Use `.github/scripts/resolve-pr-threads.sh <PR_NUMBER>` from your project root to automate thread resolution.

## Understanding Thread Resolution

**GitHub has TWO node ID types:**

- `PRRC_*` = Pull Request Review Comment (individual comment)
- `PRRT_*` = Pull Request Review Thread (conversation)

**The GraphQL `resolveReviewThread` mutation requires `PRRT_*` thread IDs, NOT `PRRC_*` comment IDs!**

**Common mistake (PR #57):**

```bash
# ❌ WRONG - Using comment node_id
gh api /repos/owner/repo/pulls/57/comments --jq '.[] | .node_id'
# Returns: PRRC_kwDOQAoSms6RlPwU (comment ID)

gh api graphql -f query='mutation {
  resolveReviewThread(input: {threadId: "PRRC_kwDOQAoSms6RlPwU"}) {...}
}'
# Error: Could not resolve to PullRequestReviewThread node
```

**✅ CORRECT - Get thread IDs via GraphQL:**

```bash
REPO_OWNER="SecPal"
REPO_NAME=".github"
PR_NUMBER=57  # Example

gh api graphql -f query="
query(\$owner: String!, \$name: String!, \$number: Int!) {
  repository(owner: \$owner, name: \$name) {
    pullRequest(number: \$number) {
      reviewThreads(first: 100) {
        nodes {
          id              # This is PRRT_* (thread ID)
          isResolved
          comments(first: 1) { nodes { body } }
        }
      }
    }
  }
}" -f owner="$REPO_OWNER" -f name="$REPO_NAME" -f number=$PR_NUMBER
# Returns: PRRT_kwDOQAoSms5eewML (thread ID)
```

See [WORKFLOW-THREAD-RESOLUTION.md](../WORKFLOW-THREAD-RESOLUTION.md) for complete examples.

## Action for Future Repos

1. Document complete review workflow in CONTRIBUTING.md
2. Add review checklist to PR template
3. Track review TODOs in issue tracker
4. One concern per PR - don't mix unrelated fixes
5. Always request review after addressing comments

**Complete Workflow Documentation:**

- [Thread Resolution Workflow](../WORKFLOW-THREAD-RESOLUTION.md) - GraphQL-based thread resolution (REQUIRED)
- Additional review workflow documentation to be created (tracked in issue tracker)

## Lessons Learned from PR #42

**Problem:** Threads not resolved after addressing comments → Enforcement check kept failing

**Root Cause:** Two separate concepts in GitHub:

1. **Comment body** (text) - can be edited
2. **Thread resolved status** (boolean) - MUST be set via GraphQL

**Solution:** Created [Thread Resolution Workflow](../WORKFLOW-THREAD-RESOLUTION.md) documentation

**Key Learning:** Addressing comments in code ≠ Resolving threads in GitHub

## Related Lessons

- [Lesson #12 (Ignoring Code Review Comments)](lesson-12.md) - Original problem
- [Lesson #16 (Review Comment Discipline)](lesson-16.md) - Meta-lesson
- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - Automated enforcement
- [Lesson #19 (Infinite Loop Prevention)](lesson-19.md) - When to request review
- [Thread Resolution Workflow](../WORKFLOW-THREAD-RESOLUTION.md) - GraphQL thread resolution (NEW)

---

**Last Updated:** 2025-10-18
**Changes:**

- Made optimized workflow PRIMARY (resolve before request, not after)
- Added automation reference (`resolve-pr-threads.sh`)
- Clarified timing guidance with rationale
