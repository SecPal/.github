<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Quick Reference - Critical Rules for AI Assistants

**🚨 READ THIS FIRST - Every Session**

This is the condensed, executable version of all critical rules. For details, see full documentation.

---

## ✅ MANDATORY: Pre-Commit Checklist

**Before EVERY commit, verify ALL items:**

```bash
# 1. Factual Accuracy
cat path/to/referenced/file.ts | grep -A 5 "function_name"
# READ actual code - don't assume!

# 2. Comprehensive Pattern Search
grep -rn "pattern_to_fix" .
# Fix ALL instances, not just one!

# 3. REUSE Compliance
reuse lint
# EVERY file needs SPDX headers (even REUSE.toml!)

# 4. Code Formatting
git diff --check  # No whitespace errors
prettier --check .  # All files formatted

# 5. No User Quotes in Docs
# ❌ "User suggested..."
# ✅ "Error handling added using try-catch pattern"
```

**Lesson Reference:** #25 (Meta-Quality)

---

## 🔄 MANDATORY: Pull Request Workflow

**CRITICAL: First vs. Subsequent Push Behavior**

### First Push (Create PR)

```bash
git push origin feature-branch

# ✅ DO: Wait 90 seconds for automatic Copilot review
# ❌ DON'T: Request review manually (causes "2 workflows awaiting approval")
```

### Subsequent Push (After Addressing Comments)

```bash
# Step 1: Fix code, commit, push
git push origin feature-branch

# Step 2: ⚠️ IMMEDIATELY request review (MANDATORY!)
mcp_github_github_request_copilot_review('SecPal', '<repo>', <PR_NUMBER>)

# Step 3: Wait for review
sleep 90

# Step 4: Check if new comments
mcp_github_github_pull_request_read(method='get_review_comments', ...)
```

**Mental Trigger:** `git push` (after first) → **STOP** → Request review!

**Lesson Reference:** #23 (Review Workflow Discipline), #19 (Infinite Loop Prevention)

---

## 🧵 MANDATORY: Thread Resolution (Before Merge)

**CRITICAL: Addressing comments in code ≠ Resolving threads in GitHub**

```bash
# Step 1: Get thread IDs (PRRT_*, NOT comment IDs PRRC_*)
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: "<repo>") {
    pullRequest(number: <PR_NUMBER>) {
      reviewThreads(first: 20) {
        nodes { id isResolved }
      }
    }
  }
}'

# Step 2: Resolve EACH thread
for thread_id in "PRRT_xxx" "PRRT_yyy"; do
  gh api graphql -f query="
  mutation {
    resolveReviewThread(input: {threadId: \"$thread_id\"}) {
      thread { id isResolved }
    }
  }"
done

# Step 3: Verify ALL resolved
# Check output: all should show "isResolved": true
```

**Lesson Reference:** #23 (Thread Resolution), WORKFLOW-THREAD-RESOLUTION.md

---

## 🚫 NEVER: Critical Anti-Patterns

| ❌ NEVER DO                                    | ✅ ALWAYS DO                        | Lesson   |
| ---------------------------------------------- | ----------------------------------- | -------- |
| `git commit --no-verify`                       | Only for bootstrap paradoxes        | #17, #22 |
| `git push --force` to main                     | Use PR workflow                     | #1, #6   |
| Request review on first push                   | Wait 90s for automatic              | #19, #23 |
| Use comment IDs (PRRC\_\*) for threads         | Use thread IDs (PRRT\_\*)           | #23      |
| Skip thread resolution before merge            | Resolve ALL threads                 | #23      |
| Modify `.license-policy.json` without approval | Ask first - it's security-critical! | #29      |
| Hardcode repo names in examples                | Use `<repo-name>` placeholders      | #25      |
| Fix only mentioned instance                    | Search & fix ALL instances          | #25      |

---

## 🔧 MANDATORY: Bash Scripts Error Handling

**ALL bash scripts in workflows MUST start with:**

```bash
#!/usr/bin/env bash
set -euo pipefail

# -e: Exit on any error
# -u: Error on undefined variables
# -o pipefail: Catch failures in pipes
```

**Lesson Reference:** #24 (Workflow Error Handling)

---

## 🏗️ Branch Protection Rules

**CRITICAL: Can't push directly to main!**

```bash
# ❌ FAILS - branch protection enabled
git push origin main

# ✅ CORRECT - PR workflow
git checkout -b feature/my-change
git push origin feature/my-change
# Create PR via MCP tools
```

**Branch Protection Requirements:**

- Pull request required
- 7 status checks must pass
- Signed commits required
- Enforces admins (no bypass!)

**Lesson Reference:** #1 (Status Check Names), #6 (Admin Bypass), #13 (No --admin flag)

---

## 🔍 Workflow Check Debugging

**If PR blocked despite all checks passing:**

```bash
# Step 1: Get actual check names
gh pr view <PR_NUMBER> --json statusCheckRollup \
  --jq '.statusCheckRollup[].name'

# Step 2: Compare with branch protection settings
# Check names MUST match EXACTLY (not "Workflow / Job", just "job-name")

# Step 3: Update branch protection if needed
# Go to GitHub Settings → Branches → main → Edit
```

**Lesson Reference:** #1, #21 (Check Names Must Match Exactly)

---

## 🔄 Workflow Re-run Pattern

**If check fails, re-run the FAILED check, not latest:**

```bash
# ❌ WRONG - re-runs latest (might be different check)
gh run rerun $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')

# ✅ CORRECT - re-run specific failed check
FAILED_RUN=$(gh run list --json databaseId,conclusion,name \
  --jq '.[] | select(.conclusion == "failure" and .name == "Target Check") | .databaseId' \
  | head -1)
gh run rerun $FAILED_RUN
```

**Lesson Reference:** #20 (Workflow Approval & Rerun)

---

## 📝 REUSE Compliance

**EVERY file needs SPDX headers (yes, even config files!):**

```
# For code files:
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

<!-- For markdown files: -->
<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->
```

**Verify before commit:**

```bash
reuse lint
# Must show: "All files compliant"
```

**Lesson Reference:** #8 (REUSE.toml Needs Headers Too)

---

## 🎯 Quality Metrics Target

**Goal:** Max 3 review cycles per PR | Target: 1 cycle, 0 comments

**Recent Results:**

- ✅ PR 45: **1 cycle, 0 comments** (perfect execution)
- ✅ PR 51: **1 cycle, 1 comment** (near perfect)
- ⚠️ PR 43: 9 cycles (baseline before quality improvements)

**Time Savings:** Quality upfront = 89% time reduction

**Lesson Reference:** #25 (Meta-Quality)

---

## 📚 When You Need More Details

**Quick Lookups:**

- Full workflows: `docs/WORKFLOWS-EXECUTABLE.md`
- Thread resolution: `docs/WORKFLOW-THREAD-RESOLUTION.md`
- All lessons: `docs/lessons/README.md` (30 lessons)
- Complete guide: `copilot-instructions.md`

**Priority Order:**

1. Read this Quick Reference first (every session)
2. Consult executable workflows for complex tasks
3. Read specific lessons when referenced
4. Use copilot-instructions.md for deep context

---

**Version:** 1.0
**Last Updated:** 2025-10-18
**Maintained In:** `.github/docs/QUICK-REFERENCE.md`
**Applies To:** All SecPal repositories

**💡 Tip:** Bookmark this file - it's your daily checklist!
