<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #1 (Branch Protection: Wrong Status Check Context Names)

**Category:** Critical Issues
**Priority:** CRITICAL
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Branch protection was configured with incorrect status check names, preventing PR merges even when all checks passed.

**What Went Wrong:**

- Branch protection used `"Workflow Name / Job Name"` format
- Example: `"Tests / contracts-tests"`, `"Code Formatting / prettier"`
- GitHub actually uses only the **job name** as the context
- Actual names: `contracts-tests`, `prettier` (without workflow prefix)
- Result: Branch protection never recognized the checks, blocking all PRs

**Root Cause:**
Assumed GitHub used the format shown in the UI (`Workflow / Job`), but the API uses just the job name.

## Solution

Updated branch protection configuration to use actual check names:

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "contracts-tests", // ✅ Correct: just the job name
      "prettier", // ✅ Not "Code Formatting / prettier"
      "reuse",
      "check-npm-licenses",
      "verify-commits"
    ]
  }
}
```

**How to Find Actual Names:**

```bash
# Get real check names from an existing PR
gh pr view <PR_NUMBER> --json statusCheckRollup --jq '.statusCheckRollup[].name'
```

## Action for Future Repos

### 1. Always Verify Check Names

Before configuring branch protection:

```bash
# Create a test PR first
# Let all workflows run
# Then extract actual check names:
gh pr view <PR> --json statusCheckRollup --jq '.statusCheckRollup[].name'
```

### 2. Update Branch Protection Templates

Ensure `.github` repository templates use correct names:

- Update `branch-protection-templates/main.json`
- Add documentation in `WORKFLOW-STATUS-CHECK-NAMES.md`

### 3. Test After Configuration

After setting branch protection:

1. Create a test PR
2. Verify all required checks appear in the PR
3. Confirm you cannot merge without checks passing

## Implementation

**Files Changed:**

- `branch-protection-main.json` - Updated contexts array

**Verification:**

```bash
# Check current branch protection
gh api repos/SecPal/contracts/branches/main/protection \
  --jq '.required_status_checks.contexts'
```

## Related Lessons

- [Lesson #21 (Branch Protection Check Names Must Match Exactly)](lesson-21.md) - Recurrence of this issue
- [Lesson #14 (Security Settings Audit)](lesson-14.md) - Cross-repo validation

## Notes

**Why This Happened:**
The GitHub UI shows checks as `Workflow Name / Job Name`, but the API uses only the job name. This discrepancy is confusing and led to misconfiguration.

**Prevented Future Issues:**

- Created `WORKFLOW-STATUS-CHECK-NAMES.md` documentation
- Added check name verification to repository setup checklist
- Lesson #21 shows this issue recurred - needs better enforcement

---

**Last Updated:** 2025-10-17
