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
   # Use MCP GitHub tool (NOT gh api)
   mcp_github_github_request_copilot_review('SecPal', '.github', 42)
   ```
5. **Address ALL comments** - fix code based on feedback
6. **Resolve ALL threads via GraphQL** (CRITICAL - see [Thread Resolution Workflow](../WORKFLOW-THREAD-RESOLUTION.md))
7. **Verify threads resolved** before merge
8. **Check enforcement passes** before merge

**Complete Workflow (MUST follow ALL steps):**

1. **First push** → Copilot reviews automatically ✅
2. **Address comments** → Fix code, commit, push
3. **Request review manually** → Use MCP tool (GraphQL)
4. **Wait for review** → Check if "no new comments"
5. **Resolve threads via GraphQL** → Mark conversations complete (see [Thread Resolution](../WORKFLOW-THREAD-RESOLUTION.md))
6. **Verify all resolved** → Check enforcement passes
7. **Rerun if race condition** → Check before review completed
8. **All green** → Merge ✅

**CRITICAL:** Step 5 (resolve threads) is REQUIRED - addressing comments in code is NOT enough!

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

**Last Updated:** 2025-10-17
