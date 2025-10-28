<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Code Review: Project Automation Workflow v2

## 📋 Overview

Comprehensive project board automation workflow that replaces all built-in GitHub Project workflows with custom, transparent, and intelligent automation.

## 🎯 Design Principles

1. **Quality First** - Extensive error handling and logging
2. **DRY** - Reusable workflow for all repositories
3. **Transparency** - All logic visible and documented
4. **Idempotency** - Safe to run multiple times
5. **Fail-safe** - Errors don't break the workflow

## 🔄 Event Coverage

### Issue Events

| Event             | Action         | Status Target        | Logic                                                                                       |
| ----------------- | -------------- | -------------------- | ------------------------------------------------------------------------------------------- |
| `issues.opened`   | Add to project | Label-based          | `enhancement` → 💡 Ideas<br>`core-feature` → 📋 Planned<br>`priority: blocker` → 📥 Backlog |
| `issues.reopened` | Add to project | 💬 Discussion        | Always goes to Discussion for re-evaluation                                                 |
| `issues.closed`   | Update status  | `state_reason`-based | `completed` → ✅ Done<br>`not_planned` → 🚫 Won't Do                                        |

### Pull Request Events

| Event                           | Condition         | Status Target  | Applies To                                    |
| ------------------------------- | ----------------- | -------------- | --------------------------------------------- |
| `pull_request.opened`           | **draft = true**  | 🚧 In Progress | Issues linked via `closes #N`                 |
| `pull_request.opened`           | **draft = false** | 👀 In Review   | Issues linked via `closes #N`                 |
| `pull_request.ready_for_review` | -                 | 👀 In Review   | Issues linked via `closes #N`                 |
| `pull_request.closed`           | merged = true     | ✅ Done        | Issues linked via `closes #N`                 |
| `pull_request.closed`           | merged = false    | _no change_    | PR abandoned/closed without merge - no update |

### Pull Request Review Events

| Event                           | Review State        | Status Target  | Applies To                    |
| ------------------------------- | ------------------- | -------------- | ----------------------------- |
| `pull_request_review.submitted` | `changes_requested` | 🚧 In Progress | Issues linked via `closes #N` |

## 🏗️ Architecture

### Job 1: `handle-issue`

**Triggers:** `issues.opened`, `issues.reopened`, `issues.closed`

**Steps:**

1. **Add to project** - Only for opened/reopened
   - Uses GraphQL `addProjectV2ItemById` mutation
   - Captures item ID for status update
   - Graceful error handling with `continue-on-error`

2. **Determine status** - Conditional logic based on:
   - Event action (opened/reopened/closed)
   - Issue labels (for new issues)
   - Close reason (for closed issues)

3. **Get project item ID** - Only for closed issues
   - Queries existing project items
   - Finds item in our project
   - Returns item ID or fails gracefully

4. **Update project status** - Conditional execution
   - Runs if: new item added OR existing item found
   - Uses GraphQL `updateProjectV2ItemFieldValue` mutation
   - Sets single-select status field

5. **Comment on issue** - User feedback
   - Confirms project assignment
   - Shows status and reason
   - Displays full status flow

### Job 2: `handle-pull-request`

**Triggers:** `pull_request.opened`, `pull_request.ready_for_review`, `pull_request.closed`

**Steps:**

1. **Extract linked issues** - Regex parsing
   - Finds `closes #123`, `fixes #456`, `resolves #789`
   - Returns array of issue numbers
   - Handles multiple linked issues

2. **Determine PR status** - Conditional logic:
   - Merged PR → ✅ Done
   - Opened/ready (not draft) → 👀 In Review
   - Draft → No action

3. **Update linked issues** - Batch processing
   - Loops through all linked issues
   - Finds each issue's project item
   - Updates status
   - Continues on individual failures

### Job 3: `handle-pr-review`

**Triggers:** `pull_request_review.submitted` with state `changes_requested`

**Steps:**

1. **Extract linked issues** - Same regex as Job 2
2. **Update to In Progress** - Signals work needed
   - Hardcoded to 🚧 In Progress status
   - Processes all linked issues
   - Fail-safe error handling

## 🔐 Secrets & Configuration

### Required Secrets

- `PROJECT_TOKEN` - Fine-grained PAT with:
  - **Organization:** Projects (Read & Write)
  - **Repository:** Issues (Read & Write)

### Environment Variables

- `PROJECT_ID`: `PVT_kwDOCUodoc4BGgjL` (SecPal Roadmap)
- `STATUS_FIELD_ID`: `PVTSSF_lADOCUodoc4BGgjLzg3iI0Y`

### Status Option IDs

```yaml
Ideas: 88b56a57 # 💡
Discussion: e2ca3f9c # 💬
Backlog: 53395960 # 📥
Planned: aa8c7fe5 # 📋
In Progress: d20ace06 # 🚧
In Review: fc39b4e9 # 👀
Done: d8103dfe # ✅
Won't Do: 6df780dd # 🚫
```

## ✅ Error Handling

### Strategy

- **Never fail the workflow** - Use `continue-on-error` and try/catch
- **Log everything** - Console output for debugging
- **Graceful degradation** - Skip failed items, continue with others
- **User feedback** - Comments explain what happened

### Example Scenarios

1. **Project add fails** → Comment on issue with manual instructions
2. **Status update fails** → Log error, but issue is still in project
3. **Linked issue not found** → Skip that issue, process others
4. **GraphQL rate limit** → Individual mutations fail, but workflow continues

## 🔄 Reusability (DRY)

### Usage in other repositories

```yaml
# .github/workflows/project-automation.yml in api/frontend/contracts
name: Project Board Automation

on:
  issues:
    types: [opened, reopened, closed]
  pull_request:
    types: [opened, ready_for_review, closed]
  pull_request_review:
    types: [submitted]

jobs:
  automate:
    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main
    secrets:
      PROJECT_TOKEN: ${{ secrets.PROJECT_TOKEN }}
```

### Benefits

- **Single source of truth** - Update once, applies everywhere
- **Consistent behavior** - All repos work the same way
- **Easy rollout** - Just add workflow call in each repo
- **Centralized testing** - Test in .github repo first

## 🧪 Test Plan

### Prerequisites

- [ ] All built-in project workflows disabled
- [ ] `PROJECT_TOKEN` secret set at repository level
- [ ] Workflow file committed and pushed

### Test Scenarios

#### 1. New Issue with Label `enhancement`

```bash
gh issue create \
  --title "Test: Enhancement → Ideas" \
  --label "enhancement" \
  --body "Should be added to project with status 💡 Ideas"
```

**Expected:**

- ✅ Issue added to project
- ✅ Status = 💡 Ideas
- ✅ Comment with status flow

#### 2. New Issue with Label `core-feature`

```bash
gh issue create \
  --title "Test: Core Feature → Planned" \
  --label "core-feature" \
  --body "Should be added with status 📋 Planned"
```

**Expected:**

- ✅ Status = 📋 Planned

#### 3. New Issue with Label `priority: blocker`

```bash
gh issue create \
  --title "Test: Blocker → Backlog" \
  --label "priority: blocker" \
  --body "Should go to 📥 Backlog"
```

**Expected:**

- ✅ Status = 📥 Backlog

#### 4. Close Issue as Completed

```bash
gh issue close 108 --reason "completed"
```

**Expected:**

- ✅ Status updated to ✅ Done

#### 5. Close Issue as Not Planned

```bash
gh issue close 109 --reason "not planned"
```

**Expected:**

- ✅ Status updated to 🚫 Won't Do

#### 6. Reopen Issue

```bash
gh issue reopen 108
```

**Expected:**

- ✅ Status updated to 💬 Discussion

#### 7. Draft PR with Linked Issue

```bash
# Create issue first
ISSUE=$(gh issue create --title "Test: Draft PR → In Progress" --label "enhancement" --body "Test draft PR workflow" --json number -q .number)

# Create DRAFT PR that closes it
git checkout -b test-draft-pr
echo "test" >> test.txt
git add test.txt
git commit -m "WIP: Test feature"
git push -u origin test-draft-pr
gh pr create \
  --draft \
  --title "WIP: Implement test feature" \
  --body "Closes #$ISSUE" \
  --head "test-draft-pr"
```

**Expected:**

- ✅ Issue status → 🚧 In Progress
- ✅ PR shows as draft

#### 8. Convert Draft to Ready for Review

```bash
# Get the PR number from previous step
PR_NUMBER=$(gh pr list --head test-draft-pr --json number -q '.[0].number')

# Mark as ready for review
gh pr ready $PR_NUMBER
```

**Expected:**

- ✅ Issue status → 👀 In Review
- ✅ PR no longer draft

#### 9. Non-Draft PR with Linked Issue (with reminder)

```bash
# Create issue
ISSUE=$(gh issue create --title "Test: Non-draft PR" --label "enhancement" --body "Test" --json number -q .number)

# Create NON-DRAFT PR
git checkout -b test-non-draft-pr
echo "test2" >> test.txt
git add test.txt
git commit -m "feat: Complete feature"
git push -u origin test-non-draft-pr
gh pr create \
  --title "feat: Complete test feature" \
  --body "Closes #$ISSUE" \
  --head "test-non-draft-pr"
```

**Expected:**

- ✅ Issue status → 👀 In Review (immediately)
- ✅ Comment on PR with draft reminder
- ⚠️ Full CI runs (vs. limited for draft)

#### 10. PR Review Requests Changes

```bash
# Request changes on any PR
PR_NUMBER=$(gh pr list --head test-non-draft-pr --json number -q '.[0].number')
gh pr review $PR_NUMBER --request-changes --body "Please fix the implementation"
```

**Expected:**

- ✅ Linked issue status → 🚧 In Progress

#### 11. Merge PR

```bash
# After fixes and approval
gh pr merge $PR_NUMBER --squash
```

**Expected:**

- ✅ Linked issue status → ✅ Done
- ✅ Issue automatically closed (by "Closes #" keyword)

#### 12. Abandoned PR (close without merge)

```bash
# Create test issue and PR
ISSUE=$(gh issue create --title "Test: Abandoned PR" --label "enhancement" --body "Test" --json number -q .number)
git checkout -b test-abandoned
echo "test3" >> test.txt
git add test.txt && git commit -m "test" && git push -u origin test-abandoned
PR=$(gh pr create --draft --title "Test" --body "Closes #$ISSUE" --json number -q .number)

# Close without merging
gh pr close $PR
```

**Expected:**

- ❌ NO status change (PR not merged)
- ✅ Issue remains in current status (🚧 In Progress from draft PR)

## ⚠️ Known Limitations

1. **Linked issue detection** - Only finds `closes/fixes/resolves #N` in PR body
   - Does NOT parse comments or commits
   - Must be in PR description

2. **Single project only** - Hardcoded to SecPal Roadmap
   - Could be made configurable with workflow inputs

3. **No conflict resolution** - If item already has status
   - Always overwrites (last write wins)
   - Could check current status first

4. **Rate limiting** - Many GraphQL mutations in sequence
   - Could hit rate limits with many linked issues
   - Currently no retry logic

## 📊 Success Criteria

- [ ] All 12 test scenarios pass
- [ ] Workflow runs without errors
- [ ] Status updates are immediate (< 30 seconds)
- [ ] Comments are helpful and accurate
- [ ] No duplicate status updates
- [ ] Error cases handled gracefully
- [ ] Logs are clear for debugging
- [ ] Draft PR reminder appears for non-draft PRs
- [ ] PR template visible when creating new PRs
- [ ] Draft PRs set issues to "In Progress"
- [ ] Non-draft PRs set issues to "In Review"

## 🚀 Rollout Plan

### Phase 1: Test in `.github` repo

1. Merge this workflow
2. Run all 12 test scenarios
3. Fix any issues found
4. Iterate until perfect

### Phase 2: Document and prepare

1. Update repository READMEs
2. Create workflow diagram
3. Write troubleshooting guide

### Phase 3: Roll out to other repos

1. Add workflow call in `api`
2. Test with real issue
3. Add to `frontend`
4. Test with real issue
5. Add to `contracts`
6. Final verification

### Phase 4: Cleanup

1. Close old test issues
2. Archive old workflow files
3. Update project documentation
4. Close related PRs

## 📝 Review Checklist

- [x] All events covered (issues, PR, PR reviews)
- [x] Error handling on all GraphQL calls
- [x] Logging for debugging
- [x] Reusable workflow structure
- [x] Clear comments explaining logic
- [x] Status IDs match project configuration
- [x] Regex patterns tested
- [x] Conditional logic is correct
- [x] No hardcoded tokens
- [x] SPDX headers present
- [ ] All test scenarios documented ✅
- [ ] Ready for commit
