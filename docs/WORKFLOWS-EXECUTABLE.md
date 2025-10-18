<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Executable Workflows - Step-by-Step Tool Call Sequences

**Purpose:** Copy-paste ready workflows with exact tool calls and verification steps.

**Target Audience:** AI assistants executing common SecPal workflows.

---

## Table of Contents

1. [Complete PR Workflow (First Time)](#complete-pr-workflow-first-time)
2. [PR Review Cycle (Subsequent Pushes)](#pr-review-cycle-subsequent-pushes)
3. [Thread Resolution Workflow](#thread-resolution-workflow)
4. [Emergency: Breaking Infinite Review Loop](#emergency-breaking-infinite-review-loop)
5. [New Repository Setup](#new-repository-setup)
6. [Cross-Repo Consistency Check](#cross-repo-consistency-check)

---

## Complete PR Workflow (First Time)

**When to use:** Creating a new PR from scratch

### Step 1: Create Feature Branch

```bash
# Tool: run_in_terminal
cd /home/user/code/SecPal/<repo>
git checkout -b feature/descriptive-name
```

### Step 2: Make Changes & Pre-Commit Validation

```bash
# Mandatory checks BEFORE commit:

# 1. Factual accuracy
grep -rn "pattern_being_changed" .

# 2. REUSE compliance
reuse lint

# 3. Formatting
prettier --check .
git diff --check

# 4. Verify claims
cat path/to/file.ts | grep -A 5 "function_name"
```

### Step 3: Commit with Signed Commit

```bash
# Tool: run_in_terminal
git add <files>
git commit -m "type(scope): descriptive message

Detailed explanation...

Changes:
- Item 1
- Item 2

Verification:
✅ Pre-commit checks passed
✅ REUSE compliant
✅ Tests passing (if applicable)"

# Pre-commit hook runs automatically
# ✅ Whitespace, Prettier, REUSE checks
```

### Step 4: First Push (Triggers Automatic Review)

```bash
# Tool: run_in_terminal
git push -u origin feature/descriptive-name

# ⏳ WAIT: Do NOT request review manually!
# Automatic review triggers in ~90 seconds
```

### Step 5: Create Pull Request

```python
# Tool: mcp_github_github_create_pull_request
mcp_github_github_create_pull_request(
    owner='SecPal',
    repo='<repo-name>',
    title='type(scope): short description',
    head='feature/descriptive-name',
    base='main',
    body='''## Summary

Brief description of changes.

## Changes

- Change 1
- Change 2

## Verification

✅ Pre-commit checks passed
✅ REUSE compliance verified
✅ All patterns searched and fixed

## Related

Lesson #XX, Issue #YY'''
)
```

### Step 6: Wait for Automatic Review (90 seconds)

```bash
# Tool: run_in_terminal
sleep 90

# Then check review status
gh pr view <PR_NUMBER> --json reviews \
  --jq '.reviews[] | {state, body}'
```

### Step 7: Check for Comments

```python
# Tool: mcp_github_github_pull_request_read
mcp_github_github_pull_request_read(
    method='get_review_comments',
    owner='SecPal',
    repo='<repo-name>',
    pullNumber=<PR_NUMBER>
)
```

**If NO comments:** → Go to Step 11 (Thread Resolution)
**If comments exist:** → Go to [PR Review Cycle](#pr-review-cycle-subsequent-pushes)

### Step 8-10: See "PR Review Cycle" below

### Step 11: Thread Resolution (MANDATORY before merge)

See [Thread Resolution Workflow](#thread-resolution-workflow)

### Step 12: Verify All Checks Pass

```bash
# Tool: run_in_terminal
gh pr view <PR_NUMBER> --json statusCheckRollup \
  --jq '.statusCheckRollup[] | "\(.conclusion // .state) - \(.name)"'

# Expected: All "SUCCESS"
```

### Step 13: Merge

```python
# Tool: mcp_github_github_merge_pull_request
mcp_github_github_merge_pull_request(
    owner='SecPal',
    repo='<repo-name>',
    pullNumber=<PR_NUMBER>,
    merge_method='squash',
    commit_title='type(scope): short description',
    commit_message='Detailed message...'
)
```

### Step 14: Cleanup

```bash
# Tool: run_in_terminal
git checkout main
git pull origin main
git branch -D feature/descriptive-name
git push origin --delete feature/descriptive-name
```

---

## PR Review Cycle (Subsequent Pushes)

**When to use:** Addressing review comments on existing PR

### Step 1: Address ALL Comments in Code

```bash
# For EACH comment:
# 1. Understand root cause
# 2. Search for ALL instances: grep -rn "pattern" .
# 3. Fix ALL occurrences in one commit
# 4. Verify fix is factually correct
```

### Step 2: Run Pre-Commit Checklist Again

```bash
# Same as first-time PR:
reuse lint
prettier --check .
git diff --check
grep -rn "pattern_to_verify" .
```

### Step 3: Commit Fixes

```bash
# Tool: run_in_terminal
git add <files>
git commit -m "fix(scope): address review comments

Addressed all X review comments:
- Comment 1: Fixed by doing Y
- Comment 2: Fixed by doing Z

Verification:
✅ All patterns searched (grep -rn ...)
✅ Factual accuracy verified
✅ Pre-commit checks passed"
```

### Step 4: Push Changes

```bash
# Tool: run_in_terminal
git push origin feature/descriptive-name
```

### Step 5: ⚠️ IMMEDIATELY Request Review (MANDATORY!)

```python
# Tool: mcp_github_github_request_copilot_review
# ⚠️ DO NOT FORGET THIS STEP!

mcp_github_github_request_copilot_review(
    owner='SecPal',
    repo='<repo-name>',
    pullNumber=<PR_NUMBER>
)

# Mental Trigger: git push → STOP → Request review!
```

### Step 6: Post Responses to Comments

````python
# Tool: mcp_github_github_add_issue_comment
# For EACH comment you addressed:

mcp_github_github_add_issue_comment(
    owner='SecPal',
    repo='<repo-name>',
    issue_number=<PR_NUMBER>,
    body='''✅ **Fixed** - <brief description>

**Changes applied:**
- Change 1
- Change 2

**Verification:**
```bash
grep -rn "pattern" .  # Found X instances, all fixed
````

'''
)

````

### Step 7: Wait for New Review

```bash
# Tool: run_in_terminal
sleep 90

# Check if new review posted
gh pr view <PR_NUMBER> --json reviews \
  --jq '.reviews | sort_by(.submittedAt) | .[-1] | {state, body}'
````

### Step 8: Check for New Comments

```python
# Tool: mcp_github_github_pull_request_read
result = mcp_github_github_pull_request_read(
    method='get_review_comments',
    owner='SecPal',
    repo='<repo-name>',
    pullNumber=<PR_NUMBER>
)

# If result shows "no new comments" → Go to Thread Resolution
# If new comments exist → Repeat from Step 1
```

### Step 9: Thread Resolution

See [Thread Resolution Workflow](#thread-resolution-workflow)

---

## Thread Resolution Workflow

**When to use:** Before merging any PR (MANDATORY!)

**CRITICAL:** Addressing comments in code ≠ Resolving threads in GitHub!

### Step 1: Get Thread IDs (NOT Comment IDs!)

```bash
# Tool: run_in_terminal
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: "<repo-name>") {
    pullRequest(number: <PR_NUMBER>) {
      reviewThreads(first: 20) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              path
              body
            }
          }
        }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes[] |
        {id, isResolved, file: .comments.nodes[0].path,
         comment: .comments.nodes[0].body[:60]}'

# Expected output: Array of threads with PRRT_* IDs
# NOTE: isResolved should be "false" for unresolved threads
```

### Step 2: Resolve Each Thread

```bash
# Tool: run_in_terminal
# For EACH thread ID from Step 1:

for thread_id in "PRRT_kwDOQAoSms5eeZxU" "PRRT_kwDOQAoSms5eeZxf" ...; do
  echo "Resolving thread: $thread_id"

  gh api graphql -f query="
  mutation {
    resolveReviewThread(input: {threadId: \"$thread_id\"}) {
      thread {
        id
        isResolved
      }
    }
  }" || echo "❌ Failed: $thread_id"
done

# Expected: Each mutation returns "isResolved": true
```

### Step 3: Verify ALL Threads Resolved

```bash
# Tool: run_in_terminal
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: "<repo-name>") {
    pullRequest(number: <PR_NUMBER>) {
      reviewThreads(first: 20) {
        nodes {
          id
          isResolved
        }
      }
    }
  }
}' --jq '.data.repository.pullRequest.reviewThreads.nodes |
        "Total: \(length) | Resolved: \(map(select(.isResolved)) | length)"'

# Expected output: "Total: N | Resolved: N" (both numbers equal!)
```

### Step 4: Re-run Failed Copilot Review Check

```bash
# Tool: run_in_terminal
# Find the FAILED check (not latest!)

FAILED_RUN=$(gh run list --branch <branch-name> \
  --json databaseId,conclusion,name \
  --jq '.[] | select(.conclusion == "failure" and
              (.name | contains("Copilot"))) | .databaseId' \
  | head -1)

echo "Re-running check: $FAILED_RUN"
gh run rerun $FAILED_RUN
```

### Step 5: Wait and Verify Check Passes

```bash
# Tool: run_in_terminal
sleep 30

gh run view $FAILED_RUN --json status,conclusion,name \
  --jq '{status, conclusion, name}'

# Expected: "conclusion": "success"
```

### Step 6: Final Verification - All Checks Green

```bash
# Tool: run_in_terminal
gh pr view <PR_NUMBER> --json statusCheckRollup \
  --jq '.statusCheckRollup[] | "\(.conclusion // .state) - \(.name)"'

# Expected: All lines show "SUCCESS"
```

**If ALL checks SUCCESS:** → Ready to merge!
**If any FAILURE:** → Debug specific check, fix, repeat

---

## Emergency: Breaking Infinite Review Loop

**When to use:** Fix → commit → review outdated → repeat (endless cycle)

**Symptoms:**

- Comments addressed in code ✅
- Push triggers new review ❌
- Review says "outdated" or finds same issues
- Cycle repeats 5+ times

**Solution: STOP the cycle**

### Step 1: STOP Making Code Changes

```
❌ DO NOT commit more code fixes!
The cycle must be broken first.
```

### Step 2: Mark Remaining Comments via API

````bash
# Tool: run_in_terminal
# For each remaining comment:

gh api -X PATCH repos/SecPal/<repo>/pulls/comments/<COMMENT_ID> \
  -f body="~~RESOLVED~~

Original comment: [original text]

**Resolution:** [Detailed justification why code is correct]

**Evidence:**
```bash
grep -A 5 "pattern" file.ts  # Shows correct implementation
````

This comment is marked resolved without additional code changes
to break infinite review loop (Lesson #19)."

````

### Step 3: Re-run Workflow WITHOUT Commit

```bash
# Tool: run_in_terminal
# HEAD SHA stays the same - no new commit!

FAILED_RUN=$(gh run list --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "failure") | .databaseId' \
  | head -1)

gh run rerun $FAILED_RUN

# Workflow re-runs with SAME code but updated comment status
````

### Step 4: Merge Immediately When Checks Pass

```bash
# Do NOT wait for another review cycle
# Merge as soon as checks turn green

gh pr view <PR_NUMBER> --json statusCheckRollup \
  --jq '.statusCheckRollup[] | select(.conclusion != "SUCCESS")'

# If empty output → All checks passed → Merge now!
```

**Lesson Reference:** #19 (Infinite Loop Prevention)

---

## New Repository Setup

**When to use:** Creating a new SecPal repository

### Step 1: Create Repository

```python
# Tool: mcp_github_github_create_repository
mcp_github_github_create_repository(
    name='repo-name',
    description='Brief description',
    private=False,  # SecPal repos are public
    autoInit=True   # Creates README
)
```

### Step 2: Clone and Setup

```bash
# Tool: run_in_terminal
cd /home/user/code/SecPal
git clone git@github.com:SecPal/repo-name.git
cd repo-name
```

### Step 3: Copy Templates from .github

```bash
# Tool: run_in_terminal
# Pre-commit hook
mkdir -p .git/hooks
cp ../.github/.github/templates/hooks/pre-commit .git/hooks/
chmod +x .git/hooks/pre-commit

# GitHub workflows
mkdir -p .github/workflows
cp ../.github/.github/templates/workflows/*.yml .github/workflows/

# Scripts
mkdir -p scripts
cp ../.github/.github/templates/scripts/* scripts/
chmod +x scripts/*.sh

# Config files
cp ../.github/.github/templates/.prettierrc.json .
cp ../.github/.github/templates/REUSE.toml .
cp ../.github/.github/templates/.license-policy.json .
```

### Step 4: Setup REUSE Compliance

```bash
# Tool: run_in_terminal
mkdir -p LICENSES
cp ../.github/LICENSES/AGPL-3.0-or-later.txt LICENSES/

# Add SPDX headers to all files (including configs!)
# Use sed or manual editing
```

### Step 5: Initial Commit

```bash
# Tool: run_in_terminal
git add .
git commit -m "chore: initial repository setup

Add SecPal standard configuration:
- Pre-commit hooks (Lesson #17)
- GitHub workflows (reusable patterns)
- REUSE compliance (Lesson #8)
- License policy (Lesson #29)
- Standard scripts

All templates copied from .github repository."

git push origin main
```

### Step 6: Configure Branch Protection

**Manual step required - GitHub API limitations**

Go to: https://github.com/SecPal/repo-name/settings/branches

Add rule for `main`:

- ✅ Require pull request before merging
- ✅ Require status checks: (copy names from existing repo)
- ✅ Require signed commits
- ✅ Include administrators
- ✅ Restrict who can push: (none - must use PRs)

**Lesson Reference:** #1, #6, #21 (Branch Protection)

---

## Cross-Repo Consistency Check

**When to use:** Quarterly audits, before major changes

### Step 1: Compare Workflow Files

```bash
# Tool: run_in_terminal
cd /home/user/code/SecPal

# Get checksum of each workflow
for repo in .github contracts; do
  echo "=== $repo ==="
  find $repo/.github/workflows -name "*.yml" -type f \
    -exec sh -c 'echo "$(md5sum {} | cut -d" " -f1) - $(basename {})"' \;
done

# Flag differences for manual review
```

### Step 2: Compare License Policies

```bash
# Tool: run_in_terminal
echo "=== Denied Licenses Comparison ==="
for repo in .github contracts; do
  echo "$repo:"
  jq -r '.deniedLicenses | join(", ")' $repo/.license-policy.json
done

# Denied licenses should be IDENTICAL across repos
```

### Step 3: Compare Script Versions

```bash
# Tool: run_in_terminal
for script in check-licenses.sh pre-commit; do
  echo "=== $script ==="
  grep -h "^# Version:" .github/scripts/$script \
                         contracts/scripts/$script 2>/dev/null \
    || echo "No version header found"
done

# Templates should be synced (same version)
```

### Step 4: Verify Branch Protection Settings

```bash
# Tool: run_in_terminal
for repo in .github contracts; do
  echo "=== $repo ==="
  gh api repos/SecPal/$repo/branches/main/protection \
    --jq '{
      required_status_checks: .required_status_checks.contexts,
      enforce_admins: .enforce_admins.enabled,
      required_pull_request: .required_pull_request_reviews != null
    }'
done

# Settings should be consistent
```

### Step 5: Document Findings

Create issue or PR with:

- Differences found
- Whether differences are intentional (repo-specific) or drift
- Action items to fix drift

**Lesson Reference:** #14 (Security Settings Audit)

---

## Summary: Key Patterns

**Pattern 1: Always verify before acting**

```bash
# ❌ DON'T assume
git commit -m "Fix function X"

# ✅ DO verify
cat file.ts | grep -A 5 "function X"  # Read actual code
git commit -m "Fix function X to handle null case"
```

**Pattern 2: Search comprehensively**

```bash
# ❌ DON'T fix one instance
sed -i 's/old/new/' file1.ts

# ✅ DO fix all instances
grep -rn "old" . | # Find all
xargs sed -i 's/old/new/'  # Fix all
```

**Pattern 3: Always request review after subsequent push**

```bash
# After git push (except first):
mcp_github_github_request_copilot_review(...)  # MANDATORY!
```

**Pattern 4: Threads must be resolved programmatically**

```bash
# ❌ WON'T WORK: Addressing in code
# ✅ REQUIRED: GraphQL mutation
gh api graphql -f query='mutation { resolveReviewThread(...) }'
```

---

**Version:** 1.0
**Last Updated:** 2025-10-18
**Maintained In:** `.github/docs/WORKFLOWS-EXECUTABLE.md`
**Companion Docs:** QUICK-REFERENCE.md, WORKFLOW-THREAD-RESOLUTION.md
