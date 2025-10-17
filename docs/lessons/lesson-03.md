<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #3 (Dependency Review: Invalid "proprietary" License Identifier)

**Category:** Critical Issues
**Priority:** HIGH
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Dependency review workflow failed because `proprietary` is not a valid SPDX license identifier.

**What Went Wrong:**

- Workflow configuration included: `deny-licenses: GPL-2.0, LGPL-2.0, LGPL-2.1, AGPL-1.0, proprietary`
- `proprietary` is not a valid SPDX identifier
- Action failed with: `##[error]Invalid license(s) in deny-licenses: proprietary`

## Solution

Remove `proprietary` from the deny list, use only valid SPDX identifiers:

```yaml
- uses: actions/dependency-review-action@v4
  with:
    fail-on-severity: moderate
    deny-licenses: GPL-2.0, LGPL-2.0, LGPL-2.1, AGPL-1.0
```

## Action for Future Repos

1. **Only use valid SPDX license identifiers** - Check https://spdx.org/licenses/
2. **Update template:** `.github/workflow-templates/dependency-review.yml`
3. **Test configuration** before applying to all repos

## Related Lessons

- [Lesson #5 (Dependabot PRs Failed Dependency Review)](lesson-05.md)
- [Lesson #10 (Dependency Graph Requires Activation)](lesson-10.md)

---

**Last Updated:** 2025-10-17
