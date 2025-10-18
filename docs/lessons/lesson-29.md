<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #29 (License Policy is Security-Critical - Never Modify Without Approval)

**Category:** Security & Compliance
**Priority:** CRITICAL
**Status:** ✅ Implemented
**Date:** 2025-10-18
**Repository:** .github, contracts

## Problem

During DRY Phase 1 & 2 implementation (PR #48), license check failures led to an attempt to modify `.license-policy.json` without proper analysis. The proposed fix was to add `UNLICENSED` to the allowed licenses list, which would have compromised security and compliance requirements.

**Critical Error:**

License-checker reported the root package as UNLICENSED and the immediate response was to allow UNLICENSED in the policy rather than investigating why the package appeared unlicensed.

**Why This Was Dangerous:**

- `.license-policy.json` is a security boundary that defines acceptable dependency licenses
- `UNLICENSED` means "all rights reserved" - fundamentally incompatible with open source
- Allowing UNLICENSED would permit any proprietary or improperly licensed dependencies
- This represents a **security and compliance decision**, not merely a technical fix

## Root Cause Analysis

**The Real Problem:**

1. Root package had `private: true` in package.json
2. license-checker tool reports private packages as UNLICENSED
3. The license check script was examining the root package itself (incorrect behavior)
4. Root package should have been excluded - only dependencies need license validation

**Correct Solutions (in order of implementation):**

1. ✅ Set `private: false` in package.json (repository is public, contains no sensitive data)
2. ✅ Exclude root package from license checking using `--excludePackages`
3. ✅ Add AGPL-3.0-or-later (the project's own license) to allowed list

**Note on `private: true` vs `private: false`:**

- **Copilot suggested**: Keep `private: true` to prevent accidental npm publication
- **Actual implementation**: Set `private: false` because:
  - Repository is public with no sensitive data
  - No intention to publish to npm (no publish workflow exists)
  - Simpler than maintaining exclude lists
  - Prevents license-checker from reporting as UNLICENSED

**Wrong Approach:**

- ❌ Adding UNLICENSED to allowed licenses (would compromise security posture)

## Critical Learning: AGPL-3.0-or-later IS Our License!

**Major Oversight:**
The license policy initially **did not include AGPL-3.0-or-later in the allowed list**, even though:

- AGPL-3.0-or-later is the project's own license (see SPDX headers)
- All our code is licensed under AGPL-3.0-or-later
- This should have been obvious from the start!

**Why It Matters:**

- AGPL-3.0-or-later (allowed) ≠ AGPL-1.0-only (denied)
- Version-specific compatibility is crucial
- AGPL-1.0-only cannot be automatically upgraded to AGPL-3.0-or-later
- Our license allows GPLv3+ compatible dependencies

## License Policy Structure

```jsonc
{
  "allowedLicenses": [
    "MIT",
    "Apache-2.0",
    "BSD-*",
    "ISC",
    "GPL-3.0-or-later",
    "LGPL-3.0-or-later",
    "AGPL-3.0", // GitHub reports reusable workflows as this
    "AGPL-3.0-or-later", // Our project license!
  ],
  "deniedLicenses": [
    "GPL-2.0-only", // Not compatible with GPLv3+
    "LGPL-2.0-only", // Not compatible with LGPLv3+
    "LGPL-2.1-only", // Not compatible with LGPLv3+
    "AGPL-1.0-only", // Ancient version, incompatible
  ],
  "description": "License policy for AGPL-3.0-or-later compatibility. AGPL-3.0-or-later is allowed as it is our project license...",
}
```

**Version Distinctions:**

- **AGPL-3.0-or-later**: Our license, fully compatible
- **AGPL-1.0-only**: Ancient, incompatible, explicitly denied
- **AGPL-3.0**: GitHub's way of reporting our workflows (also allowed)

## Rules Established

### Rule 1: Never Modify Without Explicit Approval

**NEVER** modify `.license-policy.json` without explicit user approval, even if:

- It seems like an obvious fix
- License checks are failing
- It would unblock a PR
- User is not present

**Why:**

- License policy is a **legal and compliance decision**
- Wrong decision could introduce legal liability
- User must understand implications before approving
- May require legal review in commercial contexts

### Rule 2: Understand Before Suggesting

Before proposing license policy changes:

1. ✅ Understand WHY the check is failing
2. ✅ Identify the actual problem (not just symptoms)
3. ✅ Check if project's own license is in allowed list
4. ✅ Consider non-policy solutions first
5. ✅ Explain trade-offs clearly if policy change needed

**Ask Questions First:**

- "The license check is failing because X. I see three options: A, B, C. Which approach do you prefer?"
- NOT: "I'm adding X to the allowed licenses to fix the check."

### Rule 3: Defense in Depth

For the root package issue, we implemented **two solutions**:

1. Exclude root package from checks (`--excludePackages`)
2. Add project license to allowed list (AGPL-3.0-or-later)

This prevents similar issues even if one mitigation fails.

### Rule 4: Document Rationale

When license policy IS modified (with approval):

```json
{
  "description": "License policy for AGPL-3.0-or-later compatibility. AGPL-3.0-or-later is allowed as it is our project license and meets our compatibility requirements. AGPL-1.0-only is explicitly denied because it is not compatible with AGPL-3.0-or-later and cannot be upgraded automatically..."
}
```

Clear explanations prevent future confusion.

## Bootstrap Problem: Dependency Review and Reusable Workflows

**Issue Discovered:**
When migrating to reusable workflows, dependency-review action treats workflow files as "dependencies" and checks their licenses:

```
The following dependencies have incompatible licenses:
.github/workflows/dependency-review.yml » SecPal/.github/.github/workflows/reusable-dependency-review.yml@main – License: AGPL-3.0
```

**Solution:**
Add both `AGPL-3.0` and `AGPL-3.0-or-later` to allowed list:

- Our SPDX headers say `AGPL-3.0-or-later`
- GitHub reports workflows as `AGPL-3.0` (without suffix)
- Both must be allowed for compatibility

**Related:** See Lesson #22 (Bootstrap Paradox) for using `--admin` to break circular dependencies.

## Pre-commit Hook Enhancement

Consider adding a pre-commit check:

```bash
# Check for modifications to license policy
if git diff --cached --name-only | grep -q "\.license-policy\.json"; then
  echo "⚠️  WARNING: License policy file modified"
  echo "This is a security-critical file. Ensure changes are authorized."
  echo ""
  # Don't block, just warn (policy changes ARE sometimes needed)
fi
```

## Action for Future Projects

1. **Include project's own license in allowed list from day 1**
2. Always ask before modifying license policy
3. Explain why check is failing, offer multiple solutions
4. Document rationale for all policy decisions
5. Implement defense in depth (multiple mitigations)
6. Add both AGPL-3.0 and AGPL-3.0-or-later if using reusable workflows

## Related Lessons

- [Lesson #22 (Bootstrap Paradox)](lesson-22.md) - Using --admin to break circular dependencies
- [Lesson #17 (Pre-commit Hooks)](lesson-17.md) - Automated checks
- [Lesson #27 (DRY Implementation)](lesson-27.md) - Context for this incident

## Implementation Notes

**PR #48 (.github) - 2025-10-17:**

1. License check failure detected (root package reported as UNLICENSED)
2. Incorrect fix proposed (add UNLICENSED to policy)
3. Proposal rejected - security implications recognized
4. Correct fixes implemented:
   - Set `private: false` in package.json
   - Exclude root package from license checks
   - Add AGPL-3.0-or-later (project license) to allowed list
5. Comprehensive description added to license policy
6. 4 review iterations, 23 commits total
7. All 45 review threads resolved

**PR #30 (contracts) - 2025-10-18:**

1. Dependency review failed - reusable workflows flagged as dependencies
2. GitHub reported workflows as AGPL-3.0 (without -or-later suffix)
3. Bootstrap paradox recognized (Lesson #22 pattern)
4. Added both AGPL-3.0 and AGPL-3.0-or-later to allowed list
5. Used `--admin` override to merge (fix was in the PR itself)

---

**Last Updated:** 2025-10-18
**Incident Severity:** HIGH (prevented by user intervention)
**Status:** Rules established, lesson documented
