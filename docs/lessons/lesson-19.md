<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #19 (Infinite Copilot Review Loop Prevention)

**Category:** Advanced Workflows
**Priority:** HIGH
**Status:** ✅ Implemented
**Date:** 2025-10-15
**Repository:** contracts

## Problem

PR #20 blocked for 15 commits in infinite loop:

1. Fix code → commit → HEAD changes
2. Request review → review outdated (HEAD changed)
3. New review → new comments
4. Mark `~~RESOLVED~~` → commit → back to step 1

**Root Cause:**
HEAD commit verification (Lesson #18) + iterative review = impossible to reach 0 comments while making changes.

## Solution

**Loop-Breaking Strategy:**

1. **Stop making code changes** (break the cycle)
2. **Mark ALL remaining comments `~~RESOLVED~~`** via API with justifications
3. **Re-run workflow WITHOUT commit** → HEAD stays same
4. **Merge immediately** once checks pass

```bash
# Mark comment as resolved
gh api -X PATCH repos/{owner}/{repo}/pulls/comments/{id} \
  -f body="~~RESOLVED~~ [detailed justification]"

# Re-run workflow without commit
gh run rerun {run_id}
```

## Action for Future Repos

1. Document loop-breaking strategy in workflow
2. Add troubleshooting guide
3. Consider prevention strategies (workflow changes don't require review, etc.)
4. Use `~~RESOLVED~~` appropriately (with justifications)

## Related Lessons

- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - HEAD verification causes loop
- [Lesson #22 (Bootstrap Paradox)](lesson-22.md) - Similar circular dependency
- [Lesson #23 (Review Workflow Discipline)](lesson-23.md) - When to request review

---

**Last Updated:** 2025-10-17
