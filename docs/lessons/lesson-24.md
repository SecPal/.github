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

## Additional Best Practices (PR #57)

### 1. Atomic Temporary Directory Permissions

**❌ Potential Portability Risk:**

```bash
TMPDIR=$(mktemp -d)    # Typically created with 0700 on GNU/BSD, but umask may affect this
chmod 700 "$TMPDIR"    # Ensures 0700, but a brief window may exist on affected platforms
```

**✅ Portability/Defense-in-Depth:**

```bash
TMPDIR=$(umask 077; mktemp -d)  # Ensures 0700 even on platforms/configurations where umask could affect creation
```

**Why:** Defense-in-depth measure for portability. Ensures tmpdir is only accessible to the current user even on platforms/configurations where umask could affect creation. Prevents any possibility of tmpdir containing sensitive data (API tokens, workflow contents) being readable by other users.

### 2. Guaranteed Cleanup with Trap

**❌ Manual Cleanup (Can Fail):**

```bash
TMPDIR=$(mktemp -d)
# ... do work ...
rm -rf "$TMPDIR"  # Not executed if script exits early (error, signal)
```

**✅ Trap-Based Cleanup:**

```bash
TMPDIR=$(umask 077; mktemp -d)
trap 'rm -rf -- "$TMPDIR"' EXIT INT TERM  # Runs on most errors and termination signals

# ... do work ...
# Cleanup automatic on exit
```

**Why:** `trap` ensures cleanup happens on most errors and termination signals (EXIT, INT, TERM), but not all (e.g., SIGKILL or abrupt exec).

### 3. Workflow Failure Propagation

**❌ Silent Failures (Masking Errors):**

```yaml
run: |
  set -euo pipefail
  for file in *.sh; do
    bash "$file" || echo "❌ $file failed"  # Logs but continues
  done
  # Workflow passes even if all scripts failed
```

**✅ Accumulate and Fail:**

```yaml
run: |
  set -euo pipefail
  shopt -s nullglob
  FAILED=0
  for file in *.sh; do
    if ! bash "$file"; then
      echo "❌ $file failed"
      FAILED=1
    fi
  done
  if [ "$FAILED" -ne 0 ]; then
    echo "One or more scripts failed"
    exit 1  # Workflow fails properly
  fi
```

**Why:** Ensures CI/CD fails when validation fails. Don't mask errors with `|| echo` - track them and fail explicitly.

### Complete Example (PR #57)

```bash
#!/bin/bash
set -euo pipefail
shopt -s nullglob  # Prevent literal '*.txt' if no files match

# Atomic tmpdir with guaranteed cleanup
TMPDIR=$(umask 077; mktemp -d)
trap 'rm -rf -- "$TMPDIR"' EXIT INT TERM

# Process files with failure tracking
FAILED=0
for file in *.txt; do
  if ! process_file "$file" > "$TMPDIR/$file.out"; then
    echo "❌ Failed to process $file"
    FAILED=1
  fi
done

# Cleanup automatic via trap
if [ "$FAILED" -ne 0 ]; then
  exit 1
fi
```

## Related Lessons

- [Lesson #2 (Signed Commits: GitHub API)](lesson-02.md) - Script now has error handling
- [Lesson #17 (Git State Verification)](lesson-17.md) - Pre-commit hook has it
- [Lesson #18 (Copilot Review Enforcement)](lesson-18.md) - All scripts fixed

**See Also:**

- [PR #41](https://github.com/SecPal/.github/pull/41) - Complete implementation
- [Option C Deep Audit](../CROSS-REPO-AUDIT-2025-10-16.md) - Discovery process

---

**Last Updated:** 2025-10-18
**Changes:** Added atomic tmpdir permissions, trap cleanup, workflow failure propagation (PR #57)
