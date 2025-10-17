<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #7 (package-lock.json Must Be Committed for npm Projects)

**Category:** Critical Issues
**Priority:** HIGH
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

CI failed because `package-lock.json` was gitignored, but `npm ci` requires it.

**Error:**

```
npm ci can only install packages when your package.json and package-lock.json are in sync
```

## Solution

1. Remove `package-lock.json` from `.gitignore`
2. Commit the lockfile
3. Use `npm ci` in CI/CD (faster and more reliable than `npm install`)

## Action for Future Repos

**For npm/Node.js projects:**

- ✅ Commit `package-lock.json`
- ✅ Commit `yarn.lock` (if using Yarn)
- ✅ Commit `pnpm-lock.yaml` (if using pnpm)
- ✅ Use `npm ci` / `yarn install --frozen-lockfile` in CI

**Never gitignore lockfiles** - they ensure reproducible builds.

---

**Last Updated:** 2025-10-17
