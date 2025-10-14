<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Git Hooks Templates

This directory contains reusable git hook templates for all SecPal repositories.

## Available Hooks

### pre-commit

**Purpose**: Enforces [Lesson #17 (Git State Verification)](../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions) automatically before every commit.

**Checks**:

1. **Whitespace errors** - Catches trailing spaces, wrong line endings
2. **Code formatting** - Runs Prettier to ensure consistent style
3. **Unstaged changes** - Detects formatter changes after `git add`

**Installation**:

```bash
# From repository root
cp .github/templates/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

**Verification**:

```bash
# Should see: -rwxr-xr-x
ls -la .git/hooks/pre-commit
```

**Usage**:

The hook runs automatically on every `git commit`. If checks fail, the commit is blocked with clear instructions.

**Bypass** (use sparingly):

```bash
# Skip hook for emergency commits
git commit --no-verify -m "message"
```

## Why Git Hooks?

Git hooks provide **Level 2 enforcement** in our [4-level strategy](../../docs/LESSON-ENFORCEMENT-STRATEGY.md):

- **Level 1**: Documentation (LESSONS-LEARNED) ✅
- **Level 2**: Git hooks (automated local checks) ← **You are here**
- **Level 3**: CI/CD (remote validation)
- **Level 4**: Architecture (make violations impossible)

**Real-world impact**: On 2025-10-14, we created Lesson #17 about checking git state, then immediately violated it by not running format checks before pushing. CI caught the error. The pre-commit hook prevents this cycle.

## Hook Maintenance

### Testing

```bash
# Test 1: Normal commit (should pass)
echo "test content" > test.txt
git add test.txt
git commit -m "test: verify hook"

# Test 2: Formatting issue (should fail)
# Create a file with bad formatting, commit should be blocked

# Test 3: Clean up
git reset HEAD~1
rm test.txt
```

### Updating

1. Edit template: `.github/templates/hooks/pre-commit`
2. Document changes in CHANGELOG
3. Update installed hook: `cp .github/templates/hooks/pre-commit .git/hooks/pre-commit`
4. Test thoroughly
5. Commit template changes

### Rollout to Other Repos

```bash
# 1. Copy template to target repository
cd /path/to/other-repo
cp /path/to/.github/templates/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 2. Test
echo "test" > test.txt
git add test.txt
git commit -m "test: verify hook"

# 3. Clean up test
git reset HEAD~1
rm test.txt
```

## Troubleshooting

### Hook not running

```bash
# Verify executable permission
ls -la .git/hooks/pre-commit

# Should see: -rwxr-xr-x
# If not, fix with:
chmod +x .git/hooks/pre-commit
```

### Hook too strict

If the hook blocks valid commits:

1. Check for legitimate unstaged changes: `git diff`
2. Stage them: `git add -A`
3. Retry commit

### Hook needs bypass

Only for emergencies:

```bash
git commit --no-verify -m "message"
```

**Note**: CI will still catch issues, so fix them in the next commit.

## References

- [Lesson #17: Git State Verification](../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions)
- [Lesson Enforcement Strategy](../../docs/LESSON-ENFORCEMENT-STRATEGY.md)
- [Git Hooks Documentation](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
