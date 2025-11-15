<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Bugfix: Draft PR Reminder Firing on ready_for_review Event

## Problem Description

The draft PR reminder workflow was incorrectly posting comments when a draft PR was converted to "Ready for review", not just when a new non-draft PR was opened.

**Example:** PR #158 in `api` repo received the draft reminder comment twice:

1. Once when converting from draft to ready (incorrect)
2. Once more later (incorrect)

This is confusing because:

- The PR **was** initially opened as a draft (correct workflow)
- The reminder message suggests using draft PRs for **new** PRs
- It fires after the user already followed best practices

## Root Cause

The `draft-pr-reminder.yml` workflow is called as a reusable workflow from `project-automation.yml`:

```yaml
# project-automation.yml
on:
  pull_request:
    types:
      - opened
      - ready_for_review # ⚠️ This triggers the workflow!
      - closed
      - converted_to_draft

jobs:
  draft-reminder:
    uses: SecPal/.github/.github/workflows/draft-pr-reminder.yml@main
```

**Problem:** When used as a reusable workflow (`workflow_call`), the `on:` section in `draft-pr-reminder.yml` is **ignored**. The workflow runs for ALL events from the calling workflow.

The original condition was insufficient:

```yaml
if: github.event.pull_request.draft == false
```

This only checked if the PR is not a draft, but didn't distinguish between:

- `opened` event (new non-draft PR) ✅ Should remind
- `ready_for_review` event (draft converted to ready) ❌ Should NOT remind

## Solution

Added explicit action check to the job condition:

```yaml
if: |
  github.event.pull_request.draft == false &&
  github.event.action == 'opened'
```

**Behavior after fix:**

| Event         | Draft Status   | Action               | Reminder Posted?         |
| ------------- | -------------- | -------------------- | ------------------------ |
| PR opened     | `draft: true`  | `opened`             | ❌ No (draft)            |
| PR opened     | `draft: false` | `opened`             | ✅ Yes (new non-draft)   |
| Draft → Ready | `draft: false` | `ready_for_review`   | ❌ No (was draft before) |
| Ready → Draft | `draft: true`  | `converted_to_draft` | ❌ No (is draft)         |

## Implementation Details

**Changed File:** `.github/.github/workflows/draft-pr-reminder.yml`

**DRY Compliance:** ✅
Fix is centralized in the reusable workflow and automatically applies to all repos (api, frontend, contracts) that use it.

**No changes needed in:**

- `api/.github/workflows/project-automation.yml`
- `frontend/.github/workflows/project-automation.yml`
- `contracts/.github/workflows/project-automation.yml`
- `.github/EXAMPLE_workflow_for_other_repos.yml`

All continue to use the fixed reusable workflow.

## Testing

To verify the fix works:

1. **Test Case 1: New draft PR**

   ```bash
   gh pr create --draft --title "Test: Draft PR"
   # Expected: No reminder comment
   ```

2. **Test Case 2: New non-draft PR**

   ```bash
   gh pr create --title "Test: Non-draft PR"
   # Expected: Reminder comment appears
   ```

3. **Test Case 3: Convert draft to ready**

   ```bash
   gh pr create --draft --title "Test: Draft → Ready"
   gh pr ready
   # Expected: No reminder comment on ready_for_review
   ```

## Related Issues

- Originally reported for PR #158 in `SecPal/api`
- Would have affected all repos using the reusable workflow

## Lessons Learned

1. **Reusable workflows ignore their `on:` section** - only the calling workflow's triggers matter
2. **Always check `github.event.action`** when multiple event types can trigger the same workflow
3. **Test with both direct triggers and workflow_call** - behavior differs
