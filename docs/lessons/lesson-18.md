<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #18 (Copilot Review Enforcement System)

**Category:** Advanced Workflows
**Priority:** HIGH
**Status:** ✅ Implemented
**Date:** 2025-10-15
**Repository:** .github, contracts

## Problem

PR #19 merged with 4 unresolved Copilot comments despite having enforcement workflow active - system was completely bypassed.

**Root Cause:**
Username mismatch in comment detection:

- Reviews: `copilot-pull-request-reviewer[bot]` ✅
- Comments: `Copilot` ❌ NOT detected

## Solution

**Fixed Comment Detection:**

```yaml
# Before (broken):
select(.user.login | startswith("copilot-pull-request-reviewer"))

# After (working):
select(.user.login == "Copilot" or (.user.login | startswith("copilot-pull-request-reviewer")))
```

**Added Features:**

1. HEAD commit verification - reviews must be on current commit
2. Low-confidence detection - requires `~~LOW-CONFIDENCE-ACCEPTED~~` override
3. Status outputs: `no-review`, `outdated-review`, `low-confidence`, `reviewed`

## Action for Future Repos

1. Test enforcement with real data - don't assume API field names
2. Check both reviews AND comments - different usernames
3. Require review on HEAD commit
4. Handle low confidence explicitly
5. Use `grep -F` for fixed string matching

**Implementation:**
See `.github/workflows/reusable-copilot-review.yml`

## Related Lessons

- [Lesson #16 (Review Comment Discipline)](lesson-16.md)
- [Lesson #19 (Infinite Loop Prevention)](lesson-19.md)
- [Lesson #23 (Review Workflow Discipline)](lesson-23.md)
- [Lesson #24 (Workflow Error Handling)](lesson-24.md) - Added set -euo pipefail

---

**Last Updated:** 2025-10-17
