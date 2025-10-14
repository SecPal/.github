<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Review Enforcement

This workflow ensures that all pull requests have a completed Copilot code review with **zero unresolved comments** before merging.

## Purpose

Implements **Lesson #16++ (Copilot Review Discipline)**: Make code review quality checks automatic and blocking.

## How It Works

1. **Triggers on every PR event** (open, push, review)
2. **Checks for Copilot review** existence
3. **Counts unresolved comments** (excludes comments starting with `~~RESOLVED~~`)
4. **Blocks merge** if:
   - No Copilot review found, OR
   - Any unresolved Copilot comments exist

## Required Branch Protection

To enforce this workflow, add it as a **required status check** in branch protection:

```bash
# Add to branch protection rules for 'main'
gh api -X PUT repos/SecPal/.github/branches/main/protection \
  --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Code Formatting",
      "REUSE Compliance",
      "verify-commits",
      "check-npm-licenses",
      "npm-audit",
      "actions-security",
      "dependency-review",
      "Verify Copilot Review"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

## Usage

### For PR Authors

1. **Request Copilot review** (if not automatic):

   ```bash
   # Via comment
   Comment "@copilot review" on your PR

   # Via CLI
   gh pr comment <number> --body "@copilot review"
   ```

2. **Wait ~60 seconds** for review to complete

3. **Address all comments**:
   - Fix the code issues
   - Push changes
   - Request new review to verify

4. **For false positives**:
   - Edit comment to start with `~~RESOLVED~~`
   - Add explanation why manually resolved
   - Example: `~~RESOLVED~~ This was fixed in commit abc123 - step now runs unconditionally`

### For Reviewers/Admins

- Check status: `gh pr checks <number>`
- View comments: `gh pr view <number> --comments`
- Manual resolution: Edit Copilot comment on GitHub

## Workflow Integration

This workflow runs **in parallel** with other CI checks:

- Does NOT block CI (they run concurrently)
- Provides **fast feedback** (~10-30 seconds after Copilot review)
- Clear **actionable error messages** when blocked

## Metrics

Track Copilot review effectiveness:

```bash
# Count PRs blocked by Copilot comments
gh pr list --state all --json number,reviews,statusCheckRollup \
  --jq '.[] | select(.statusCheckRollup[] | select(.name == "Verify Copilot Review" and .conclusion == "FAILURE")) | .number'
```

## Related

- [Lesson #16: Review Comment Discipline](../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-16)
- [PR Structure Guidelines](../../docs/PR-STRUCTURE-GUIDELINES.md)
- [Copilot Review Process](../../docs/COPILOT-REVIEW-PROCESS.md) _(to be created)_

## Maintenance

**Update frequency:** Review quarterly

- Adjust comment detection logic if Copilot changes format
- Add additional validation rules as needed
- Monitor false positive rate

---

**Implementation Date:** 2025-10-14
**Status:** Active enforcement on all PRs
**Effectiveness:** TBD (track metrics after 1 month)
