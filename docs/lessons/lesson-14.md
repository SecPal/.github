<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #14 (Security Settings Audit: Inconsistencies Between Repositories)

**Category:** Process Issues
**Priority:** MEDIUM
**Status:** ✅ Documented
**Date:** 2025-10-12
**Repository:** .github

## Problem

Security audit revealed critical discrepancies between `.github` and `contracts` repositories after implementing security improvements only in contracts.

**Key Findings:**
| Setting | .github | contracts | Impact |
|---------|---------|-----------|--------|
| required_signatures | ❌ false | ✅ true | Unsigned commits allowed |
| required_linear_history | ❌ false | ✅ true | Merge commits allowed |
| actions-security check | ❌ Missing | ✅ Present | No unpinned action detection |
| Action versions | v4 | v5 | Outdated versions |

**Root Cause:**
Applied lessons to contracts but didn't sync back to .github - no cross-repo audit process.

## Solution

**Comprehensive security audit:**

```bash
# 1. Compare branch protection
gh api repos/SecPal/.github/branches/main/protection | jq '{enforce_admins, required_signatures, required_linear_history}'
gh api repos/SecPal/contracts/branches/main/protection | jq '{enforce_admins, required_signatures, required_linear_history}'

# 2. Compare workflows
diff .github/workflows/security.yml contracts/.github/workflows/security.yml
```

**Applied Fixes:**

1. Enabled required_signatures and required_linear_history via API
2. Added actions-security job
3. Updated all actions v4 → v5
4. Updated documentation to match reality

## Action for Future Repos

1. **Regular cross-repo security audits** (quarterly)
2. Apply security improvements to ALL repos simultaneously
3. Verify documentation matches actual settings
4. Create audit checklist

## Related Lessons

- [Lesson #1 (Branch Protection: Check Names)](lesson-01.md)
- [Lesson #6 (Branch Protection: Admin Bypass)](lesson-06.md)
- [Option B Cross-Repo Audit (2025-10-16)](../CROSS-REPO-AUDIT-2025-10-16.md)

---

**Last Updated:** 2025-10-17
