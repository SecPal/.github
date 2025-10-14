<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Pre-Commit Hook Installation Guide

**Purpose:** Automatic enforcement of [Lesson #17 (Git State Verification)](../../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions)

---

## Quick Installation

### For any SecPal repository:

```bash
# From the repository root
curl -o .git/hooks/pre-commit https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Or if you have `.github` repo cloned locally:

```bash
# From the repository root
cp /path/to/.github/.github/templates/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

---

## Verification

```bash
# Check hook is executable
ls -lah .git/hooks/pre-commit
# Should show: -rwxr-xr-x ... pre-commit

# Test with a simple commit
echo "# Test" > test.txt
git add test.txt
git commit -m "test: verify hook"
# Should see: "🔍 Pre-commit Hook: Running checks..."

# Clean up
git reset HEAD~1
rm test.txt
```

---

## What Does This Hook Do?

### Check 1: Whitespace Errors

- Trailing spaces at end of lines
- Wrong line endings (CRLF vs LF)
- Mixed tabs and spaces

### Check 2: Code Formatting (Prettier)

- Runs `npm run format:check` if package.json exists
- Ensures all files match Prettier configuration
- Blocks commit if formatting would change files

### Check 3: Unstaged Changes

- **The critical check for Lesson #17!**
- Detects if formatters ran after `git add`
- Prevents incomplete git state

---

## Technology-Specific Behavior

### Node.js / TypeScript / React Projects

**Works perfectly!** ✅

```bash
# Hook checks:
npm run format:check  # Uses your Prettier config
```

**Requirements:**

- `package.json` must have `format:check` script
- Prettier configured (already in SecPal standard)

**Example package.json:**

```json
{
  "scripts": {
    "format": "prettier --write .",
    "format:check": "prettier --check ."
  }
}
```

---

### PHP / Laravel Projects

**Works with minor adaptation!** ✅

The hook will:

- ✅ Check whitespace errors (always works)
- ⚠️ Skip Prettier check if no package.json found
- ✅ Check unstaged changes (always works)

**To enable full formatting checks in Laravel:**

**Option A: Add Prettier for Blade templates**

```bash
# Add Prettier with Blade plugin
npm install --save-dev prettier @shufo/prettier-plugin-blade

# Add to package.json
{
  "scripts": {
    "format": "prettier --write 'resources/**/*.blade.php' '*.php'",
    "format:check": "prettier --check 'resources/**/*.blade.php' '*.php'"
  }
}
```

**Option B: Use PHP-CS-Fixer**

Modify the hook to use PHP-CS-Fixer instead:

```bash
# In pre-commit hook, replace Prettier section with:
if [ -f "composer.json" ] && composer show | grep -q "php-cs-fixer"; then
  echo "🎨 Checking PHP code formatting..."
  vendor/bin/php-cs-fixer fix --dry-run --diff
fi
```

**Recommendation:** Use Option A (Prettier) for consistency across all SecPal repos.

---

### Python Projects

**Works with adaptation!** ✅

Replace Prettier check with Black:

```bash
# In pre-commit hook, replace Prettier section with:
if [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  echo "🎨 Checking Python code formatting..."
  if command -v black &> /dev/null; then
    black --check .
  else
    echo "⚠️  Warning: black not installed"
  fi
fi
```

---

### Go Projects

**Works with adaptation!** ✅

Replace Prettier check with gofmt:

```bash
# In pre-commit hook, replace Prettier section with:
if [ -f "go.mod" ]; then
  echo "🎨 Checking Go code formatting..."
  unformatted=$(gofmt -l .)
  if [ -n "$unformatted" ]; then
    echo "❌ Unformatted files:"
    echo "$unformatted"
    exit 1
  fi
fi
```

---

## Bypass (Emergency Only)

If you absolutely must commit without running checks:

```bash
git commit --no-verify -m "emergency: bypass hook"
```

**⚠️ Warning:** CI will still run the same checks! Bypassing locally just delays the failure.

---

## Troubleshooting

### Hook not running?

```bash
# Check permissions
ls -lah .git/hooks/pre-commit

# Should be executable (-rwxr-xr-x)
# If not:
chmod +x .git/hooks/pre-commit
```

### "npm: command not found"?

```bash
# Hook requires Node.js for Prettier
# Install Node.js or skip formatting check by commenting out that section
```

### Hook blocks valid commit?

```bash
# Check what's wrong:
git status        # Unstaged changes?
git diff          # What changed?
npm run format    # Fix formatting
git add -A        # Stage fixes
git commit        # Try again
```

---

## Standard Setup for New SecPal Repos

### 1. Initial Repository Setup

```bash
# Clone template or create new repo
gh repo create SecPal/new-repo --public --clone

cd new-repo

# Install pre-commit hook
curl -o .git/hooks/pre-commit https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### 2. Add Prettier Configuration

```bash
# Copy from .github repo
curl -o .prettierrc https://raw.githubusercontent.com/SecPal/.github/main/.prettierrc
curl -o .prettierignore https://raw.githubusercontent.com/SecPal/.github/main/.prettierignore
```

### 3. Add package.json Scripts

```json
{
  "name": "new-repo",
  "scripts": {
    "format": "prettier --write .",
    "format:check": "prettier --check ."
  },
  "devDependencies": {
    "prettier": "^3.0.0"
  }
}
```

### 4. Test Hook

```bash
echo "# Test" > test.txt
git add test.txt
git commit -m "test: verify setup"
# Should see hook running

git reset HEAD~1
rm test.txt
```

---

## Related Documentation

- [Lesson #17: Git State Verification](../../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions)
- [Pre-Commit Hook Template](./pre-commit)
- [Repository Setup Guide](../../../docs/REPOSITORY-SETUP-GUIDE.md)

---

## Changelog

| Date       | Change                           | Author |
| ---------- | -------------------------------- | ------ |
| 2025-10-14 | Created installation guide       | Agent  |
| 2025-10-14 | Added Laravel/PHP support notes  | Agent  |
| 2025-10-14 | Added Python/Go adaptation notes | Agent  |

---

**Last Updated:** 2025-10-14
**Status:** Active - Use for all new SecPal repositories
