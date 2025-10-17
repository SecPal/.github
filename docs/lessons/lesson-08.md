<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #8 (REUSE.toml Itself Needs SPDX Headers)

**Category:** Critical Issues
**Priority:** MEDIUM
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

REUSE compliance check reported "22 / 23 files compliant" - the missing file was `REUSE.toml` itself!

## Solution

Add SPDX headers to REUSE.toml:

```toml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

version = 1
SPDX-PackageName = "SecPal Contracts"
# ... rest of config
```

## Action for Future Repos

1. Add SPDX headers to `REUSE.toml` template
2. Add to REUSE compliance checklist
3. Run `reuse lint` locally before first commit

---

**Last Updated:** 2025-10-17
