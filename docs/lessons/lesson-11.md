<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #11 (Inconsistent Pre-Commit Validation)

**Category:** Process Issues
**Priority:** MEDIUM
**Status:** ✅ Documented
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Repeated pattern of incomplete commits causing CI failures:

- PR #6: Committed without running format check → CI failed on prettier
- PR #10: Ran `npm install` but didn't check `git status` → Uncommitted package-lock.json

## Solution

**Created validation scripts:**

```json
{
  "scripts": {
    "check": "npm test && npm run validate && npm run format:check && npm run build",
    "ci": "npm ci && npm test && npm run validate && npm run format:check && npm run build"
  }
}
```

**Mandatory Pre-Commit Workflow:**

1. `git status` - What changed?
2. `git diff` - Are all changes intentional?
3. `npm run check` - Do all tests pass?
4. `git status` - Did tests modify files?
5. Review and stage any test-modified files
6. `git commit -S`
7. `git status` - Working tree clean?
8. `git push` - Only if clean

## Action for Future Repos

1. Add `check` and `ci` scripts to package.json template
2. Install pre-commit hook (see Lesson #17)
3. Document workflow in README
4. Add `.license-policy.json` for license validation

## Related Lessons

- [Lesson #17 (Git State Verification)](lesson-17.md) - Automated enforcement via pre-commit hook
- [Lesson #12 (Ignoring Code Review Comments)](lesson-12.md)

---

**Last Updated:** 2025-10-17
