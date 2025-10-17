<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson #2 (Signed Commits: `git verify-commit` Doesn't Work in GitHub Actions)

**Category:** Critical Issues
**Priority:** CRITICAL
**Status:** ✅ Fixed
**Date:** 2025-10-11
**Repository:** contracts

## Problem

Workflow attempted to verify GPG signatures using `git verify-commit`, but all signed commits failed verification in GitHub Actions.

**What Went Wrong:**

- Workflow used `git verify-commit $commit` to verify GPG signatures
- GPG public keys are not available in Actions checkout environment
- Git cannot verify signatures without the public keys
- Result: All legitimately signed commits failed the check

**Root Cause:**
GitHub Actions doesn't have access to users' GPG public keys. The `git verify-commit` command requires the public key to be in the local GPG keyring.

## Solution

Use GitHub API instead of local git verification:

```yaml
- name: Verify all commits are signed
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    set -euo pipefail
    commits=$(gh api repos/${{ github.repository }}/pulls/${{ github.event.pull_request.number }}/commits --jq '.[].sha')

    for commit in $commits; do
      verified=$(gh api repos/${{ github.repository }}/commits/$commit --jq '.commit.verification.verified')
      if [[ "$verified" != "true" ]]; then
        echo "❌ Commit $commit is not signed!"
        exit 1
      fi
    done
```

**Why This Works:**
GitHub has already verified the signatures server-side. We just query the verification status via API.

## Action for Future Repos

### 1. Update Workflow Template

Replace local git verification with GitHub API:

**File:** `.github/workflow-templates/signed-commits.yml`

```yaml
- name: Verify all commits are signed
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    set -euo pipefail

    # Get all commits in the PR
    commits=$(gh api repos/${{ github.repository }}/pulls/${{ github.event.pull_request.number }}/commits --jq '.[].sha')

    # Check each commit's verification status
    for commit in $commits; do
      verified=$(gh api repos/${{ github.repository }}/commits/$commit --jq '.commit.verification.verified')

      if [[ "$verified" != "true" ]]; then
        echo "❌ Commit $commit is not signed!"
        exit 1
      fi
    done

    echo "✅ All commits are signed"
```

### 2. Remove Old Approach

**Do NOT use:**

```bash
# ❌ This doesn't work in GitHub Actions
git verify-commit $commit
```

## Implementation

**Files Changed:**

- `.github/workflows/signed-commits.yml` - Switched to GitHub API
- `.github/workflow-templates/signed-commits.yml` - Updated template

**Verification:**

```bash
# Test the workflow by creating a PR with signed commits
# Check workflow logs show "✅ All commits are signed"
```

## Related Lessons

- [Lesson #4 (Dependabot PRs Failed Signed Commits Check)](lesson-04.md) - Dependabot doesn't sign commits
- [Lesson #24 (Workflow Error Handling)](lesson-24.md) - Added `set -euo pipefail` to this script

## Notes

**GitHub's Verification:**
GitHub performs GPG verification server-side when commits are pushed. The API exposes this verification status, making it the reliable source of truth in Actions.

**Advantages of API Approach:**

- No need to import GPG keys
- Works for all users automatically
- Leverages GitHub's existing verification
- More secure (no key management in workflows)

---

**Last Updated:** 2025-10-17
