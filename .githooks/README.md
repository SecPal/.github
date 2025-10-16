<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Git Hooks

This directory contains tracked git hooks that should be installed in your local `.git/hooks/` directory.

## Installation

After cloning the repository, run:

```bash
# Install all hooks
cp .githooks/* .git/hooks/
chmod +x .git/hooks/pre-commit
```

Or configure git to use this directory:

```bash
git config core.hooksPath .githooks
```

## Available Hooks

### pre-commit

**Purpose:** Enforce Lesson #17 (Git State Verification) by catching common issues before commit.

**Checks performed:**

- ✅ Whitespace errors (trailing spaces, incorrect line endings)
- ✅ Code formatting (Prettier)
- ✅ REUSE compliance (SPDX headers, license files)
- ✅ Unstaged changes detection (catches formatter-induced changes)

**Why this matters:**

- Prevents CI failures from formatting issues
- Catches license compliance problems early
- Detects when formatters modify files after `git add`

**Synchronized with:** `SecPal/contracts` repository

## Synchronization

These hooks are synchronized across both repositories:

- `SecPal/.github`
- `SecPal/contracts`

When updating hooks, ensure changes are applied to both repos (or centralized via DRY approach).

## Related Documentation

- Lesson #17: Git State Verification (Pre-commit Hooks)
- Contributing Guide: `.github/CONTRIBUTING.md`
- REUSE Compliance: `REUSE.toml`
