<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #12 (Ignoring Code Review Comments)

**Category:** Process Issues
**Priority:** HIGH
**Status:** ✅ Documented
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Merged PR #2 without reading Copilot review comments - had to create follow-up PR #3 to address suggestions.

**What Went Wrong:**

- Copilot provided 2 suggestions (unclear terminology, missing cross-references)
- Merged without checking review comments
- Only discovered after merge when user pointed it out
- Created unnecessary follow-up PR

## Solution

**Mandatory PR Review Workflow:**

```bash
# 1. Check for review comments
gh pr view <PR> --comments

# 2. Check inline code review comments
gh api repos/<owner>/<repo>/pulls/<PR>/comments --jq '.[] | {path, line, body}'

# 3. Address ALL comments before merging
# 4. Only merge after comments addressed
```

**Key Insight:**
"If you are conducting a review—even if it's not required, because you are working alone—you should always pay attention to this information!"

## Action for Future Repos

1. Always check review comments before merging
2. Add "Review comments addressed?" to pre-merge checklist
3. Treat bot reviews with same importance as human reviews
4. Document in CONTRIBUTING.md

## Related Lessons

- [Lesson #16 (Review Comment Discipline)](lesson-16.md) - Meta-lesson about this
- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - Automated enforcement
- [Lesson #23 (Review Workflow Discipline)](lesson-23.md) - Complete workflow

---

**Last Updated:** 2025-10-17
