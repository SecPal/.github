<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Development Workflow Scripts

**Purpose:** Automated enforcement of Lesson #17 (Git State Verification)

---

## Quick Reference

```bash
# BEFORE starting new work
./scripts/pre-work-check.sh

# AFTER every commit
./scripts/post-commit-check.sh
```

---

## Scripts

### `pre-work-check.sh` - Start Work Safely

**Run before:** Creating new feature branch

**What it does:**

- ✅ Verifies no uncommitted changes
- ✅ Updates main branch from origin
- ✅ Ensures clean base for new work
- ✅ Prevents merge conflicts from stale base

**Usage:**

```bash
./scripts/pre-work-check.sh
git checkout -b feature/your-feature
```

**Prevents:**

- Merge conflicts (like PR #19 incident)
- Forgetting to update main
- Starting work with dirty state

---

### `post-commit-check.sh` - Verify Clean State

**Run after:** Every `git commit`

**What it does:**

- ✅ Checks for uncommitted changes
- ✅ Checks for untracked files (temp files!)
- ✅ Checks for unstaged changes (formatter detection)
- ✅ Shows branch sync status

**Usage:**

```bash
git commit -m "feat: add feature"
./scripts/post-commit-check.sh
```

**Catches:**

- Untracked temp files (like `pr-body-fixed.md`)
- Formatter-induced changes
- Incomplete commits
- Forgotten files

---

## Workflow Integration

### Recommended Workflow

```bash
# 1. Before starting work
./scripts/pre-work-check.sh
git checkout -b feature/my-feature

# 2. Do your work
vim file.ts

# 3. Commit
git add -A
git commit -m "feat: implement feature"

# 4. Verify clean state (MANDATORY!)
./scripts/post-commit-check.sh

# 5. If clean, safe to continue or push
git push -u origin feature/my-feature
```

### Shell Aliases (Optional)

Add to your `.zshrc` or `.bashrc`:

```bash
# Pre-work check
alias gstart='./scripts/pre-work-check.sh'

# Post-commit check (run after every commit!)
alias gcheck='./scripts/post-commit-check.sh'

# Combined: commit + check
gcommit() {
  git commit "$@" && ./scripts/post-commit-check.sh
}
```

---

## Why These Scripts Exist

### The Problem (Real Incident - PR #19)

**What happened:**

1. Created feature branch from stale main (before PR #18 merged)
2. PR #18 added `REPOSITORY-SETUP-GUIDE.md`
3. My branch also modified same file
4. Result: **MERGE CONFLICT**

**Also:** 5. Created temp file `pr-body-fixed.md` 6. Forgot to delete it 7. Left untracked file in repo 8. **Lesson #17 violation** while documenting Lesson #17!

### The Solution

**Pre-Work Script** prevents conflicts:

```bash
./scripts/pre-work-check.sh
# Ensures: main is up-to-date BEFORE creating branch
```

**Post-Commit Script** prevents forgotten files:

```bash
./scripts/post-commit-check.sh
# Catches: untracked files, unstaged changes
```

---

## Exit Codes

Both scripts use exit codes for automation:

- **0** = Success, all checks passed
- **1** = Failure, action required

Use in CI/CD:

```yaml
- name: Verify clean state
  run: ./scripts/post-commit-check.sh
```

---

## Related Documentation

- [Lesson #17: Git State Verification](../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions)
- [Pre-Commit Hook](../.github/templates/hooks/pre-commit)
- [Repository Setup Guide](../docs/REPOSITORY-SETUP-GUIDE.md)

---

## Changelog

| Date       | Change                                  | Author |
| ---------- | --------------------------------------- | ------ |
| 2025-10-14 | Created pre-work and post-commit checks | Agent  |

---

**Last Updated:** 2025-10-14
**Status:** Active - Use in all SecPal repositories
