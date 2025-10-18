<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #13 (Using `--admin` to Bypass Branch Protection)

**Category:** Process Issues
**Priority:** HIGH
**Status:** ✅ Documented
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Used `gh pr merge --admin` to bypass "Branch is not up to date" protection instead of waiting for proper resolution. This defeats the purpose of `enforce_admins: true`.

**What Went Wrong:**

- PR #8: Branch protection blocked merge (out of date)
- Instead of waiting for Dependabot rebase, used `--admin` to bypass
- Also ignored Dependabot warning about missing "contracts" label
- Admin bypass nullifies all carefully configured protections

## Solution

**Never use `--admin` for normal merges:**

```bash
# ❌ WRONG
gh pr merge <PR> --admin

# ✅ CORRECT - Wait for proper resolution
gh pr comment <PR> --body "@dependabot rebase"
# Wait for rebase, verify checks, then merge normally
```

**Address warnings:**

```bash
# Create missing labels
gh label create "contracts" --color "0366d6" --description "Contracts dependencies"
```

**Key Insight:**
If tempted to use `--admin`, the correct answer is usually: **wait and fix properly**.

## Valid Use Case: Bootstrap Paradoxes

**Exception:** Bootstrap paradoxes (see Lesson #22) are valid use cases for `--admin`:

- Fix is IN the PR but checks run with `@main` (which doesn't have the fix)
- Check fails BECAUSE the fix isn't in main yet
- Can't merge because check fails → can't get fix into main
- This is a circular dependency that REQUIRES `--admin` to break

**Example:** PR adds AGPL-3.0 to license policy, but dependency-review (running with main's policy) flags the PR itself for not having AGPL-3.0 allowed.

## Action for Future Repos

1. Reserve `--admin` for bootstrap paradoxes ONLY (Lesson #22)
2. For normal issues: Wait and fix properly
3. Create all required labels during setup
4. Address ALL warnings before merging
5. Add "No admin bypass used?" to pre-merge checklist
6. If using `--admin`: Document WHY in commit/PR description

## Related Lessons

- [Lesson #6 (Branch Protection: Admin Bypass)](lesson-06.md) - Why we set enforce_admins: true
- [Lesson #21 (Branch Protection Names Must Match)](lesson-21.md)
- [Lesson #22 (Bootstrap Paradox)](lesson-22.md) - Valid use case for --admin
- [Lesson #29 (License Policy)](lesson-29.md) - Bootstrap example with dependency-review

---

**Last Updated:** 2025-10-17
