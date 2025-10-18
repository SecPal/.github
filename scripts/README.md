<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Automation Scripts

This directory contains **two categories** of scripts:

1. **Workflow Scripts** - Git state verification (Lesson #17)
2. **Quality Scripts** - Code/docs validation (PR #58 learnings)

---

## 📋 Quick Reference

### Before/After Commits

```bash
# BEFORE starting new work
./scripts/pre-work-check.sh

# AFTER every commit
./scripts/post-commit-check.sh
```

### Documentation Quality (runs via pre-commit)

```bash
# Validate bash blocks in markdown
./scripts/shellcheck-docs.sh docs/**/*.md

# Detect hardcoded values
./scripts/check-hardcoded-examples.sh docs/**/*.md

# Validate GraphQL queries
./scripts/validate-graphql-docs.sh docs/**/*.md
```

---

## 🔧 Workflow Scripts

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
# Checks: No uncommitted/untracked files after commit
```

---

## 📚 Quality Scripts (NEW)

### `shellcheck-docs.sh` - Bash Linting for Documentation

**Purpose:** Extract and validate bash code blocks from markdown files.

**Catches:**

- Missing `shopt -s nullglob` before glob patterns
- Piped `while` loops (subshell exit issues)
- `mktemp` without atomic permissions
- Missing trap cleanup
- `rm -rf` without `--` protection
- `read` without `-r` flag
- All standard shellcheck violations

**Usage:**

```bash
./scripts/shellcheck-docs.sh docs/**/*.md
```

**Exit:** `0` = pass, `1` = violations found
**Tests:** `tests/shellcheck-docs.bats` (14 tests)
**Prevents:** 40% of review comments (PR #58 analysis)

---

### `check-hardcoded-examples.sh` - Hardcoding Detector

**Purpose:** Detect hardcoded values in documentation examples.

**Catches:**

- Hardcoded PR/issue numbers (`PR_NUMBER=42`)
- Hardcoded owners/repos (`owner: "SecPal"`)
- Incorrect markdown escaping (`PRRT*\*` → use `` `PRRT_*` ``)
- Non-parameterized GraphQL queries

**Exceptions:** Lines with `Example:`, `e.g.,`, `# example` ignored

**Usage:**

```bash
./scripts/check-hardcoded-examples.sh docs/**/*.md
```

**Exit:** `0` = pass, `1` = hardcoding found
**Tests:** `tests/check-hardcoded-examples.bats` (8 tests)
**Prevents:** 20% of review comments (PR #58 analysis)

---

### `validate-graphql-docs.sh` - GraphQL Query Validator

**Purpose:** Validate GraphQL queries in documentation.

**Catches:**

- Single-quoted queries with variables (won't expand)
- Variables used but not declared
- Hardcoded values instead of variables
- Pagination without `pageInfo`
- Mismatched braces

**Usage:**

```bash
./scripts/validate-graphql-docs.sh docs/**/*.md
```

**Exit:** `0` = valid, `1` = invalid
**Tests:** `tests/validate-graphql-docs.bats` (7 tests)
**Prevents:** 13% of review comments (PR #58 analysis)

---

### `validate-prevention-strategy.sh` - Repository Audit

**Purpose:** Validate prevention measures in repositories.

**Checks:**

- Branch protection (enforce_admins)
- Required status checks
- Copilot Review enforcement
- Reusable workflows

**Usage:**

```bash
./scripts/validate-prevention-strategy.sh SecPal/.github
```

---

## 🎯 Impact Metrics

**Total Automation Coverage:** 73% of historical review comments preventable

| Script                   | Prevents    | Source |
| ------------------------ | ----------- | ------ |
| shellcheck-docs          | 12/30 (40%) | PR #58 |
| check-hardcoded-examples | 6/30 (20%)  | PR #58 |
| validate-graphql-docs    | 4/30 (13%)  | PR #58 |

---

## 🧪 Testing

**Run tests:**

```bash
# Install bats
npm install -g bats

# Run all tests
bats tests/*.bats

# Run specific test
bats tests/shellcheck-docs.bats
```

**Test coverage:**

- ✅ Positive cases (should pass)
- ✅ Negative cases (should fail)
- ✅ Edge cases (no blocks, multiple files)

---

## 📖 Related Documentation

- [PR #58 Analysis](../docs/pr-analysis/pr-58-analysis.md) - Motivation
- [PR Analysis Framework](../docs/PR-ANALYSIS-FRAMEWORK.md) - Methodology
- [Lesson #17](../docs/lessons/lesson-17.md) - Git state verification
- [Lesson #24](../docs/lessons/lesson-24.md) - Bash patterns
- [Lesson #25](../docs/lessons/lesson-25.md) - Pre-commit checklist

---

**Last Updated:** 2025-10-18
**Maintainers:** SecPal Contributors

---

## Exit Codes

Both scripts use exit codes for automation:

- **0** = Success, all checks passed
- **1** = Failure, action required

Use in CI/CD:

````yaml
```yaml
```yaml
- name: Verify clean state
  run: ./scripts/post-commit-check.sh
````

```

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
