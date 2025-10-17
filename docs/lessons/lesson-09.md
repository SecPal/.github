<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #9 (Deprecated Dependencies from Jest)

**Category:** Critical Issues
**Priority:** MEDIUM
**Status:** ✅ Documented
**Date:** 2025-10-11
**Repository:** contracts

## Problem

`npm ci` showed deprecation warnings for transitive dependencies from Jest:

- `inflight@1.0.6` - "This module is not supported, and leaks memory"
- `glob@7.2.3` - "Glob versions prior to v9 are no longer supported"

These are **transitive dependencies** from Jest 29.7.0, not our direct dependencies.

## Solution

- Updated `@redocly/cli` 1.x → 2.x (fixed their glob usage)
- Accepted Jest warnings for now (no security issues, waiting for Jest team to update)
- Considered alternative testing frameworks if it becomes problematic

## Action for Future Repos

1. Check for deprecated dependencies during setup
2. Update direct dependencies to latest major versions
3. Document known deprecated transitive dependencies
4. Accept transitive deprecations if no security risk

---

**Last Updated:** 2025-10-17
