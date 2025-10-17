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
4. **Copilot review AFTER each change push:**
   ```bash
   # After pushing changes
   gh api -X POST repos/SecPal/.github/pulls/$PR/requested_reviewers \
     -f reviewers='["copilot-pull-request-reviewer[bot]"]'
   ```
5. **Address ALL comments before requesting new review**
6. **Check enforcement** before merge

**Key Workflow:**

- First push → Copilot reviews automatically ✅
- Subsequent pushes → Request review manually ✅
- Check status → Rerun if raced ✅
- All comments addressed → Merge ✅

## Action for Future Repos

1. Document complete review workflow in CONTRIBUTING.md
2. Add review checklist to PR template
3. Track review TODOs in issue tracker
4. One concern per PR - don't mix unrelated fixes
5. Always request review after addressing comments

**Complete Workflow:**
See [Review Workflow Documentation (to be created)](https://github.com/SecPal/.github/issues/new?title=Create+Review+Workflow+Documentation&labels=documentation) – documentation is tracked as a future issue and is not yet available.

## Related Lessons

- [Lesson #12 (Ignoring Code Review Comments)](lesson-12.md) - Original problem
- [Lesson #16 (Review Comment Discipline)](lesson-16.md) - Meta-lesson
- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - Automated enforcement
- [Lesson #19 (Infinite Loop Prevention)](lesson-19.md) - When to request review

---

**Last Updated:** 2025-10-17
