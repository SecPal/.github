<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #21 (Branch Protection Check Names Must Match Exactly)

**Category:** Advanced Workflows
**Priority:** CRITICAL
**Status:** ✅ Implemented
**Date:** 2025-10-15
**Repository:** .github, contracts

## Problem

PR #26 couldn't merge despite all checks passing - GraphQL error: "Required status check 'Verify Copilot Review' is expected".

**Root Cause:**
Check name mismatch:

- Required: `"Verify Copilot Review"`
- Actual: `"Verify Copilot Review / Verify Copilot Review"`

GitHub check matching is **exact and case-sensitive**.

## Solution

**Always verify actual check names:**

```bash
# Get real check names from PR
gh pr view <PR> --json statusCheckRollup --jq '.statusCheckRollup[].name'
```

**Update branch protection with exact names:**

```json
{
  "contexts": [
    "Verify Copilot Review / Verify Copilot Review", // Includes job name
    "prettier", // Just job name
    "reuse"
  ]
}
```

**Check Naming Rules:**

- Format: `<workflow-name> / <job-name>` (reusable workflows)
- Sometimes: Just `<job-name>` (simple workflows)
- **Exact match required** - no wildcards

## Action for Future Repos

1. **Always verify** check names from actual PR before configuring protection
2. Update branch protection when workflow structure changes
3. Test protection works by creating test PR
4. Document check names in `WORKFLOW-STATUS-CHECK-NAMES.md`

**This is a recurrence of Lesson #1** - needs better enforcement!

## Related Lessons

- [Lesson #1 (Branch Protection: Wrong Check Names)](lesson-01.md) - Original discovery
- [Lesson #14 (Security Settings Audit)](lesson-14.md) - Cross-repo validation
- [Option B Cross-Repo Audit](../CROSS-REPO-AUDIT-2025-10-16.md) - Found this recurrence

---

**Last Updated:** 2025-10-17
