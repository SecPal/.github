<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #17 (Git State Verification After Work Sessions)

**Category:** Meta-Lessons
**Priority:** MEDIUM
**Status:** ✅ Implemented
**Date:** 2025-10-14
**Repository:** .github

## Problem

Created Lesson #15/16 about discipline, then immediately violated it - committed without checking formatting, CI failed.

**What Happened:**

1. Documented lessons about checking work before committing
2. Made changes to implement those lessons
3. Committed without running `npm run format:check`
4. CI failed on prettier check
5. Had to create follow-up commit

**Irony:** Documented the solution while demonstrating the problem!

## Solution

**Pre-commit Hook for Automated Enforcement:**

```bash
#!/bin/bash
# .git/hooks/pre-commit
set -euo pipefail

# 1. Check whitespace errors
git diff-index --check --cached HEAD -- || exit 1

# 2. Check code formatting
npm run format:check || {
  echo "❌ Prettier check failed. Run: npm run format"
  exit 1
}

# 3. Check for unstaged changes
if ! git diff --quiet; then
  echo "⚠️  Unstaged changes detected after formatting!"
  echo "Run: git status"
  exit 1
fi
```

**Installation:**

```bash
cp .github/templates/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Action for Future Repos

1. Include pre-commit hook template in .github repo
2. Add hook installation to repository setup checklist
3. Document in README.md
4. Hook enforces Lessons #11, #15, #16, #17 automatically

## Related Lessons

- [Lesson #11 (Inconsistent Pre-Commit Validation)](lesson-11.md)
- [Lesson #24 (Workflow Error Handling)](lesson-24.md) - Added set -euo pipefail to hook

---

**Last Updated:** 2025-10-17
