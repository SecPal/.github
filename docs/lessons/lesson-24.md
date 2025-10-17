<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #24 (Workflow Error Handling: set -euo pipefail)

**Category:** Recent Additions
**Priority:** CRITICAL
**Status:** ✅ Implemented
**Date:** 2025-10-17
**Repository:** .github

## Problem

Deep workflow audit (Option C) discovered 7 of 9 workflows missing strict error handling - bash scripts could **silently fail**.

**What Went Wrong:**

```bash
# WITHOUT set -e (DANGEROUS)
DENIED=$(jq '.deniedLicenses' missing-file.json)  # Fails, but script continues
echo "denied=$DENIED" >> $GITHUB_OUTPUT          # Sets empty value
# Workflow passes ✅ but didn't actually check anything ❌
```

**Impact:**
Critical workflows (dependency-review, license-check, signed-commits, security scanning) could pass even when commands failed → **false sense of security**.

## Solution

Add `set -euo pipefail` to ALL bash scripts in workflows:

```yaml
- name: Check something
  run: |
    set -euo pipefail  # ← ADD THIS LINE

    # Rest of script
    DENIED=$(jq '.deniedLicenses' .license-policy.json)
    echo "denied=$DENIED" >> $GITHUB_OUTPUT
```

**What it does:**

- `-e`: Exit immediately if any command fails
- `-u`: Error on undefined variables (catches typos)
- `-o pipefail`: Catch failures in pipes (`cmd1 | cmd2`)

**Fixed Workflows (PR #41):**

1. `dependency-review.yml`
2. `license-check.yml`
3. `reusable-copilot-review.yml` (3 scripts)
4. `reusable-dependency-review.yml` (2 scripts)
5. `reusable-license-check.yml`
6. `security.yml`
7. `signed-commits.yml`

## Action for Future Repos

1. **ALWAYS** add `set -euo pipefail` to bash scripts in workflows
2. Add to workflow templates
3. Audit existing workflows for missing error handling
4. Test workflows fail properly when commands error

**Template:**

```yaml
run: |
  set -euo pipefail
  # Your script here
```

## Related Lessons

- [Lesson #2 (Signed Commits: GitHub API)](lesson-02.md) - Script now has error handling
- [Lesson #17 (Git State Verification)](lesson-17.md) - Pre-commit hook has it
- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - All scripts fixed

**See Also:**

- [PR #41](https://github.com/SecPal/.github/pull/41) - Complete implementation
- [Option C Deep Audit](../CROSS-REPO-AUDIT-2025-10-16.md) - Discovery process

---

**Last Updated:** 2025-10-17
