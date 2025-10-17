<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #6 (Branch Protection: Admin Bypass Enabled)

**Category:** Critical Issues
**Priority:** CRITICAL
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Branch protection had `enforce_admins: false`, allowing repository admins to bypass ALL protection rules, defeating the purpose of branch protection for solo maintainers.

## Solution

Enable admin enforcement while allowing self-merge:

```json
{
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": true
  }
}
```

**Rationale:**

- `enforce_admins: true` - Admins must follow all rules
- `required_approving_review_count: 0` - Solo maintainer can merge own PRs (after checks pass)
- This ensures checks MUST pass, even for admins

## Action for Future Repos

1. Set `enforce_admins: true` in all branch protection configs
2. Set review count to 0 for solo maintainer workflows
3. Never use `--admin` to bypass checks (see Lesson #13)

## Related Lessons

- [Lesson #1 (Branch Protection: Check Names)](lesson-01.md)
- [Lesson #13 (Using --admin to Bypass)](lesson-13.md)
- [Lesson #21 (Branch Protection Names Must Match)](lesson-21.md)

---

**Last Updated:** 2025-10-17
