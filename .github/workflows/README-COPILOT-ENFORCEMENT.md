<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Review Enforcement

This workflow ensures that all pull requests have a completed Copilot code review with **zero unresolved comments** before merging.

## Purpose

Implements **Lesson #18 (Copilot Review Enforcement System)**: Make code review quality checks automatic and blocking with proper username detection, HEAD commit verification, and low-confidence handling.

## How It Works

1. **Triggers on every PR event** (open, push, review, comment)
2. **Checks for Copilot review** existence on HEAD commit
3. **Verifies review is current** (on HEAD commit, not outdated)
4. **Detects low-confidence reviews** (with override mechanism)
5. **Counts unresolved comments** (excludes comments starting with `~~RESOLVED~~`)
6. **Blocks merge** if:
   - No Copilot review found, OR
   - Review is outdated (not on HEAD commit), OR
   - Review has low confidence (without override), OR
   - Any unresolved Copilot comments exist

### Key Features (Lesson #18 + #19)

- **Dual username detection**: Handles both `"Copilot"` (comments) and `"copilot-pull-request-reviewer"` (reviews)
- **HEAD commit verification**: Ensures review is on current code, not old commits
- **Low-confidence override**: `~~LOW-CONFIDENCE-ACCEPTED~~` in PR description for docs-only changes
- **Comment resolution pattern**: `~~RESOLVED~~` prefix for manual resolution with justification
- **Infinite loop prevention**: Re-run without commit after marking comments (see Lesson #19)

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

   **Recommended: Via MCP tool** (when using GitHub Copilot Chat in VS Code):

   ```
   @github-pull-request Request a Copilot review for this PR
   ```

   The tool `mcp_github_github_request_copilot_review` is more reliable than comment-based requests.

   **Alternative: Via comment**:

   ```bash
   # Via GitHub web interface
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

- [Lesson #16: Review Comment Discipline](../docs/LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-16)
- [PR Structure Guidelines](../docs/PR-STRUCTURE-GUIDELINES.md)
- [Copilot Review Process](../docs/COPILOT-REVIEW-PROCESS.md) _(to be created)_

## Maintenance

**Update frequency:** Review quarterly

- Adjust comment detection logic if Copilot changes format
- Add additional validation rules as needed
- Monitor false positive rate

---

**Implementation Date:** 2025-10-14
**Status:** Active enforcement on all PRs
**Effectiveness:** TBD (track metrics after 1 month)
