<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #10 (Dependency Graph Requires Explicit Activation)

**Category:** Issues to Be Aware Of
**Priority:** MEDIUM
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

`dependency-review-action` failed with "Dependency review is not supported on this repository" even though the repository is public.

**Root Cause:**
Dependency Graph was not automatically enabled - requires manual activation.

## Solution

Enable via GitHub Settings:

1. Navigate to: `https://github.com/SecPal/<repo>/settings/security_analysis`
2. Enable "Dependency graph"

Or via API:

```bash
gh api -X PATCH repos/SecPal/contracts -f has_vulnerability_alerts=true
```

**Note:** May still require manual web UI activation in some cases.

## Action for Future Repos

1. Add "Enable Dependency Graph" to repository setup checklist
2. Include direct link in setup documentation
3. Verify activation before configuring dependency-review workflow

## Related Lessons

- [Lesson #3 (Dependency Review: Invalid License)](lesson-03.md)
- [Lesson #5 (Dependabot PRs Failed Dependency Review)](lesson-05.md)

---

**Last Updated:** 2025-10-17
