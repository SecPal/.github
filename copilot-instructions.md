<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Instructions for SecPal Organization

**Scope:** All SecPal repositories (`.github`, `contracts`, future repos)
**Purpose:** Organization-wide guidelines for GitHub Copilot Chat and Pull Request Reviewer
**Version:** 2.3 (Enhanced Review Workflow Clarity)

---

## 🚨 START HERE - Essential Rules

**⚠️ NEW AI ASSISTANTS: Read [Lesson #0](/.github/docs/lessons/lesson-00.md) FIRST!**

Critical rules you MUST follow:

1. ✅ **Quality First**: Systematic review before commit - NEVER blindly accept suggestions!
2. ✅ **Branch Protection**: Always create PR branch, NEVER push to main
3. ✅ **Pre-commit Hook**: NEVER use `--no-verify` except bootstrap paradoxes (Lesson #22)
4. ✅ **Review Workflow**: Fix code → Commit → Push → Respond to comments → Request review (Lesson #23)
5. ✅ **Thread Resolution**: Addressing code ≠ Resolving threads (needs GraphQL, see WORKFLOW-THREAD-RESOLUTION.md)
6. ✅ **Lesson Writing**: No user quotes, English only, document patterns not conversations
7. ✅ **License Policy**: Never modify `.license-policy.json` without approval

**Full details:** [Lesson #0 - Start Here](/.github/docs/lessons/lesson-00.md)

---

## 🏢 Organization Overview

SecPal is a platform for private security services with multiple repositories:

- **`.github`**: Shared configurations, reusable workflows, lessons learned, documentation (26+ lessons)
- **`contracts`**: Smart contracts, blockchain integration (Solidity/TypeScript, Hardhat)
- **Future repos**: API (Laravel/PHP), frontend, infrastructure

**Core Principle:** All repositories follow the same quality standards, workflows, and best practices documented in `.github/docs/lessons/`.

---

## 🎯 Quality-First Philosophy (Lesson #25)

**Goal:** Max 3 review cycles per PR | Target: 1 cycle, 0 comments

**Recent Success:**

- ✅ PR 45: **1 cycle, 0 comments** (perfect execution)
- ✅ PR 44: 4 cycles (56% improvement over baseline)
- ⚠️ PR 43: 9 cycles (baseline before quality improvements)

**Time Savings:** Quality upfront = 89% time reduction (PR 45 vs PR 43)

---

## ✅ Pre-Commit Quality Checklist (Mandatory)

**BEFORE every commit**, complete ALL checks:

### 1. Factual Accuracy (Lesson #25)

```bash
# READ actual code being referenced - don't assume!
cat path/to/file.ts | grep -A 5 "function_name"

# Verify claims in documentation match reality
# Example: Doc says "Step 3 has pattern X" → READ Step 3 to confirm
```

**Why:** Fixes based on unverified assumptions caused errors in PR 43 Review 8

### 2. Comprehensive Pattern Search (Lesson #25)

```bash
# Find ALL instances of a pattern, not just one
grep -rn "pattern_to_fix" .

# Fix ALL occurrences in single commit
# Don't wait for reviews to find remaining instances
```

**Examples:**

- Hardcoded repo names (`SecPal`, `contracts`)
- Hardcoded PR numbers (`42`, `43`)
- Inconsistent link text
- Duplicate code patterns

### 3. Style Consistency

```bash
# Match existing format
grep -A 3 "similar_function" existing_file.ts

# Check naming conventions
grep -rn "class.*Name" src/

# Verify indentation/spacing matches
```

**Apply to:**

- Function naming (camelCase, PascalCase, kebab-case)
- Comment style (inline, block, JSDoc)
- File organization (imports, exports, sections)
- Documentation structure (headings, lists, code blocks)

### 4. Link Verification

```bash
# Test all file path references
ls -la path/mentioned/in/doc.md

# Verify cross-references exist
grep -l "lesson-XX" docs/lessons/*.md

# Check URLs resolve (if external)
```

### 5. No User Quotes (Lesson #25)

**❌ DON'T:**

- "User suggested adding error handling"
- "Based on feedback from review"
- Quote conversation history

**✅ DO:**

- "Error handling added using try-catch pattern"
- "Implemented based on standard practice"
- Document solutions and patterns

### 6. REUSE Compliance (Lesson #8)

```bash
# Add SPDX headers to ALL files (including config files)
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Verify compliance before commit
reuse lint
```

**Note:** Even `REUSE.toml` itself needs SPDX headers!

### 7. Bash Script Error Handling (Lesson #24)

**CRITICAL:** ALL bash scripts in workflows MUST include:

```bash
set -euo pipefail

# -e: Exit on any error
# -u: Error on undefined variables
# -o pipefail: Catch failures in pipes
```

**Why:** 7 of 9 workflows lacked this → scripts could silently fail

---

## 🔄 Pull Request Workflow (Lesson #23)

### Complete PR Lifecycle

```
1. Create branch → Make changes → Commit
2. Push (FIRST time) → Automatic Copilot review ✅
3. Review has comments? → Fix code → Commit → Push
4. Push (SUBSEQUENT) → Request review MANUALLY ⚠️
5. Repeat steps 3-4 until "no new comments"
6. Resolve threads via GraphQL (REQUIRED)
7. Verify enforcement passes → Merge
```

### Critical Timing Rules (Lesson #19, #23)

#### First Push

```bash
git push origin feature-branch

# ✅ DO: Wait 90 seconds for automatic review
# ❌ DON'T: Request review manually (causes "2 workflows awaiting approval")
```

#### Subsequent Pushes

```bash
git push origin feature-branch

# ✅ DO: Request review immediately via MCP
mcp_github_github_request_copilot_review('SecPal', 'repo-name', PR_NUMBER)

# ❌ DON'T: Forget to request (common error, requires manual intervention)
```

**Mental Trigger:** `git push` (after first) → **IMMEDIATELY** think "Review request!"

### Thread Resolution (Lesson #23, WORKFLOW-THREAD-RESOLUTION.md)

**CRITICAL:** Addressing comments in code ≠ Resolving threads in GitHub

**Two separate concepts:**

1. **Comment body** (text) - editable via REST API
2. **Thread resolved status** (boolean) - ONLY via GraphQL

**Complete Workflow:**

```bash
# Step 1: Get unresolved thread IDs
gh api /repos/SecPal/repo/pulls/PR_NUMBER/comments --jq '.[] | {
  id: .id,
  node_id: .node_id,
  path: .path,
  body: .body
}'

# Step 2: Resolve each thread via GraphQL
THREAD_ID="PRRC_kwDOQAoSms6RVnL7"

RESULT=$(gh api graphql -f query="
mutation {
  resolveReviewThread(input: {threadId: \"$THREAD_ID\"}) {
    thread { id isResolved }
  }
}
" 2>&1)

# Step 3: Verify success (check for errors)
if echo "$RESULT" | jq -e '.errors' > /dev/null 2>&1; then
  echo "❌ Failed to resolve thread $THREAD_ID"
  exit 1
else
  echo "✅ Thread resolved"
fi

# Step 4: Verify all threads resolved
gh api /repos/SecPal/repo/pulls/PR_NUMBER/comments \
  --jq 'map(select(.in_reply_to_id == null)) | map({id, node_id, body})'
```

**See:** `.github/docs/WORKFLOW-THREAD-RESOLUTION.md` for complete script

### Breaking Infinite Loops (Lesson #19)

If caught in review loop (fix → commit → review outdated → repeat):

**Solution:**

1. **STOP making code changes** (break the cycle)
2. Mark remaining comments `~~RESOLVED~~` via API with justifications
3. Re-run workflow WITHOUT commit (HEAD stays same)
4. Merge immediately once checks pass

```bash
# Mark comment as resolved (don't commit!)
gh api -X PATCH repos/SecPal/repo/pulls/comments/COMMENT_ID \
  -f body="~~RESOLVED~~ [detailed justification of why code is correct]"

# Re-run failed check without commit
FAILED_RUN=$(gh run list --json databaseId,conclusion \
  --jq '.[] | select(.conclusion == "failure") | .databaseId' | head -1)
gh run rerun $FAILED_RUN
```

---

## ❌ Critical Anti-Patterns

### Process Violations

| ❌ DON'T                                  | ✅ DO                          | Lesson   |
| ----------------------------------------- | ------------------------------ | -------- |
| Request review on first push              | Wait for automatic review      | #19, #23 |
| Use `--admin` to bypass branch protection | Wait for proper resolution     | #13      |
| Rerun "latest" check                      | Rerun FAILED check by ID       | #20      |
| Use `git commit --no-verify` regularly    | Only for true emergencies      | #17      |
| Skip thread resolution                    | Always use GraphQL workflow    | #23      |
| Forget review request on subsequent push  | Immediately request after push | #25      |

### Code Quality Violations

| ❌ DON'T                            | ✅ DO                             | Lesson |
| ----------------------------------- | --------------------------------- | ------ |
| Hardcode values in examples         | Use variables/generics            | #25    |
| Fix only mentioned instance         | Search and fix ALL instances      | #25    |
| Skip factual verification           | Read actual code being referenced | #25    |
| Omit `set -euo pipefail` in scripts | Add to ALL bash scripts           | #24    |
| Commit without REUSE headers        | Add SPDX to ALL files             | #8     |

### Documentation Violations

| ❌ DON'T                     | ✅ DO                           | Lesson |
| ---------------------------- | ------------------------------- | ------ |
| Quote users in documentation | Document patterns and solutions | #25    |
| Write conversation history   | Write reusable knowledge        | #25    |
| Use inconsistent terminology | Match existing terms exactly    | #25    |
| Skip cross-references        | Link related lessons/docs       | #16    |

---

## 📂 Repository-Specific Guidelines

### `.github` Repository

**Purpose:** Shared configurations, reusable workflows, lessons learned

**Structure:**

```
.github/
├── workflows/          # Reusable GitHub Actions
├── .github/templates/  # Templates for all repos (hooks, workflows, etc.)
└── docs/
    ├── lessons/        # 26+ lessons learned (lesson-01.md to lesson-26.md)
    ├── WORKFLOW-*.md   # Workflow documentation
    └── *.md            # Setup guides, audits, etc.
```

**When Working Here:**

1. **Creating New Lessons:**

   ```bash
   # Check highest existing lesson number
   ls docs/lessons/ | grep -oP 'lesson-\K\d+' | sort -n | tail -1

   # Create next lesson (e.g., lesson-27.md)
   # Follow template: Problem → Solution → Action → Related Lessons
   ```

2. **Update Lesson Index:**
   - Add entry to `docs/lessons/README.md` category table
   - Update statistics (total lessons, priorities, status)
   - Add cross-references to related lessons

3. **Lesson Naming Convention:**
   - Use `lesson-XX.md` format (zero-padded to 2 digits)
   - Title: "Lesson #XX (Short Descriptive Title)"
   - Categories: Critical Issues, Process Issues, Meta-Lessons, Advanced Workflows, Recent Additions

4. **Quality Standards:**
   - English only (consistency)
   - No user quotes (document solutions)
   - Self-contained (understandable independently)
   - Cross-reference related lessons

**Key Files:**

- `.github/workflows/reusable-copilot-review.yml` - Review enforcement (Lesson #18)
- `.github/templates/hooks/pre-commit` - Pre-commit validation (Lesson #17)
- `docs/lessons/README.md` - Lesson index (26 lessons)

### `contracts` Repository

**Purpose:** Smart contracts (Solidity), tests, deployment scripts

**Stack:** Hardhat, TypeScript, Solidity 0.8+

**Structure:**

```
contracts/
├── contracts/      # Solidity smart contracts
├── test/           # Mirror contracts/ structure
├── scripts/        # Deployment scripts
└── hardhat.config.ts
```

**When Working Here:**

1. **Testing:**

   ```bash
   npm test              # Run all tests
   npm run test:gas      # Check gas usage
   npm run coverage      # Test coverage report
   ```

2. **Security Considerations:**
   - Reentrancy protection (use ReentrancyGuard)
   - Integer overflow/underflow (Solidity 0.8+ has built-in checks)
   - Access control (use OpenZeppelin Ownable/AccessControl)
   - Event emission (all state changes)

3. **Gas Optimization:**
   - Document trade-offs in comments
   - Use `uint256` instead of smaller uints (unless packing)
   - Cache storage reads in memory
   - Use `calldata` for external function parameters

4. **Code Style:**
   - Follow Solidity Style Guide
   - NatSpec comments for all public functions
   - Test file naming: `ContractName.test.ts`

**REUSE Compliance:**

```solidity
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

### Future Repositories (API, Frontend)

**Setup Steps:** See `.github/docs/REPOSITORY-SETUP-GUIDE.md`

**Mandatory for ALL repos:**

1. License & REUSE compliance
2. Pre-commit hook installation
3. Prettier configuration
4. GitHub Actions (Copilot review, signed commits, license check)
5. Branch protection (enforce admins, require reviews, status checks)

---

## 🔗 Essential Resources

### Quick Reference (By Topic)

**Quality & Process:**

- Lesson #25: Pre-commit quality checklist (MUST READ)
- Lesson #17: Pre-commit hook installation
- Lesson #23: Complete review workflow
- Lesson #16: Review comment discipline

**Workflow & Automation:**

- Lesson #18: Copilot review enforcement system
- Lesson #19: Breaking infinite review loops
- Lesson #24: Bash error handling (`set -euo pipefail`)
- WORKFLOW-THREAD-RESOLUTION.md: GraphQL thread resolution

**Branch Protection:**

- Lesson #1: Status check context names (must match exactly)
- Lesson #6: Admin bypass disabled (`enforce_admins: true`)
- Lesson #13: Never use `--admin` flag
- Lesson #21: Check names must match exactly (recurrence of #1)

**Dependencies & Security:**

- Lesson #2: Signed commits in GitHub Actions
- Lesson #3: Dependency review license identifiers
- Lesson #4: Dependabot PRs and signed commits
- Lesson #5: Dependabot PRs and dependency review
- Lesson #26: Dependabot exception for Copilot review

**REUSE & Licensing:**

- Lesson #8: REUSE.toml needs SPDX headers too
- Lesson #7: package-lock.json must be committed

**All Lessons:** `.github/docs/lessons/README.md` (26 lessons, categorized)

### Documentation Standards

**Universal (All Repos):**

- English only (organizational consistency)
- No user quotes (document solutions, not conversations)
- Focus on reusable patterns (not one-time fixes)
- Self-contained documents (understandable independently)
- Cross-reference related docs/lessons

**Code Comments:**

- Explain WHY, not WHAT (code shows what)
- Document trade-offs (security vs. gas, readability vs. performance)
- Link to relevant lessons when applicable
- Use TODO/FIXME/NOTE consistently

---

## 📊 Success Metrics & Benchmarks

### Target Performance (All Repositories)

| Metric                           | Target | Baseline  | Source          |
| -------------------------------- | ------ | --------- | --------------- |
| Review cycles per PR             | ≤ 3    | 9 cycles  | Lesson #25      |
| Factual errors                   | 0      | Multiple  | Lesson #25      |
| Forgotten review requests        | 0      | Common    | Lesson #19, #25 |
| Unresolved threads at merge      | 0      | 9 threads | Lesson #23      |
| Bash scripts with error handling | 100%   | 22% (2/9) | Lesson #24      |

### Recent Benchmarks (.github Repository)

**PR 45 (2025-10-17):** 🏆 GOLD STANDARD

- 1 review cycle
- 0 comments
- 0 threads
- Merged in < 2 hours
- Perfect application of Lesson #25 checklist

**PR 44 (2025-10-17):** ✅ GOOD

- 4 review cycles
- 56% improvement over PR 43
- Applied new quality processes

**PR 43 (2025-10-16):** ⚠️ BASELINE

- 9 review cycles
- Recurring errors (superficial fixes, forgotten reviews, unverified facts)
- Led to creation of Lesson #25

**Key Learning:** PR 45 vs PR 43 = **89% time savings** through quality-first approach

---

## 🚀 Quality-First Development Workflow

### Starting Any Task

```
1. 📚 Read Context
   └─ Search existing lessons for related issues
   └─ Review docs/CONTRIBUTING.md for repo-specific rules
   └─ Check recent PRs for patterns

2. 🔍 Verify Facts
   └─ grep/read actual code being referenced
   └─ Test commands/links work as documented
   └─ Verify claims against reality (don't assume)

3. 🔎 Check Patterns
   └─ Search ENTIRE codebase (not just one file)
   └─ Use: grep -rn "pattern" .
   └─ Fix ALL instances in one commit

4. 🎨 Match Style
   └─ Existing naming conventions
   └─ File organization patterns
   └─ Documentation structure
   └─ Comment style

5. ✅ Self-Review
   └─ Apply complete pre-commit checklist
   └─ Verify REUSE compliance (reuse lint)
   └─ Run tests (if applicable)
   └─ Format code (prettier --check .)

6. 📝 Commit Message
   └─ Detailed description of changes
   └─ Verification steps performed
   └─ Reference lessons applied
   └─ Sign commit (GPG/SSH)

7. 🚢 Push & Review
   └─ First push: Wait 90s for automatic review
   └─ Subsequent: Request review IMMEDIATELY
   └─ Address ALL comments comprehensively
   └─ Resolve threads via GraphQL
   └─ Merge when all green
```

### Addressing Review Comments (Comprehensive Mode)

**For EACH comment:**

```
1. Understand root cause (not just surface symptom)
2. Search for ALL instances: grep -rn "pattern" .
3. Verify fix is factually correct (read code!)
4. Check related code/docs for similar issues
5. Update ALL affected locations in one commit
6. Document reasoning (if non-obvious)
```

**After fixing ALL comments:**

```
1. Re-run entire pre-commit checklist
2. Write detailed commit message
3. Push changes
4. Request review (if subsequent push)
5. Wait for "no new comments"
6. Resolve ALL threads via GraphQL
7. Verify enforcement passes
8. Merge
```

---

## 🛠️ Common Scenarios & Solutions

### Scenario: Branch Protection Blocking Merge

**Symptoms:**

- All checks pass ✅
- PR still can't merge ❌
- "Required status check missing"

**Solution (Lesson #1, #21):**

```bash
# Get actual check names from PR
gh pr view PR_NUMBER --json statusCheckRollup \
  --jq '.statusCheckRollup[].name'

# Update branch protection to match EXACTLY
# ❌ WRONG: "Workflow Name / Job Name"
# ✅ CORRECT: "job-name-only"
```

### Scenario: Copilot Review Keeps Failing

**Symptoms:**

- Comments addressed in code ✅
- "X unresolved threads" ❌

**Solution (Lesson #23):**

```bash
# Addressing comments ≠ Resolving threads
# MUST use GraphQL mutation

# See: .github/docs/WORKFLOW-THREAD-RESOLUTION.md
```

### Scenario: Infinite Review Loop

**Symptoms:**

- Fix code → commit → review outdated
- Repeat endlessly

**Solution (Lesson #19):**

```bash
# STOP committing!
# Mark comments ~~RESOLVED~~ via API (no commit)
# Re-run workflow with unchanged HEAD
# Merge immediately
```

### Scenario: Workflow Silent Failure

**Symptoms:**

- Workflow passes ✅
- Check didn't actually run 🤔

**Solution (Lesson #24):**

```yaml
# Add to ALL bash scripts in workflows:
run: |
  set -euo pipefail
  # Rest of script
```

### Scenario: REUSE Check Failing

**Symptoms:**

- "X / Y files compliant"
- Unknown which file

**Solution (Lesson #8):**

```bash
# Run locally to find missing headers
reuse lint

# Add SPDX headers to ALL files (including REUSE.toml!)
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
```

---

## 📚 Advanced Topics

### Creating Reusable Workflows (Lesson #22)

**Bootstrap Paradox:** Can't enforce Copilot review on workflow that creates enforcement

**Solution:**

- Use GraphQL API to resolve threads on workflow changes
- Accept one-time `~~LOW-CONFIDENCE-ACCEPTED~~` for bootstrap PR
- All subsequent PRs use enforced workflow

### Security Audit Process (Lesson #14)

**Cross-Repository Consistency Check:**

```bash
# Compare settings across all repos
gh api repos/SecPal/repo1/branches/main/protection > repo1.json
gh api repos/SecPal/repo2/branches/main/protection > repo2.json
diff -u repo1.json repo2.json
```

### Dependabot Special Handling (Lesson #4, #5, #26)

**Dependabot PRs automatically exempt from Copilot review** (Lesson #26):

- **Auto-detection**: Workflow checks if `github.event.pull_request.user.login == 'dependabot[bot]'`
- **Auto-pass**: Copilot review check passes automatically for Dependabot PRs
- **Rationale**: Dependency updates are machine-generated, no human code to review
- **Alternative QA**: All other CI checks remain active (tests, security scans, license checks)

**Additional Dependabot considerations:**

- Signed commit verification skip (bot can't sign) - Lesson #4
- Dependency review license allowlist - Lesson #5
- Proper labels for categorization
- Consider `@dependabot merge` for approved PRs

**When to Exempt PRs from Review** (Lesson #26 Best Practices):

✅ **Good candidates for exemption:**

- Automated dependency updates (Dependabot, Renovate)
- Automated security patches
- Lock file updates with no code changes

❌ **Should NOT be exempted:**

- Human-authored code changes
- Configuration updates that affect behavior
- Automated code generation that modifies logic
- PRs from unknown/untrusted automation

**Key Principle**: "Not all PRs are equal - automated updates need different workflows than human code"

**Implementation**: See `.github/workflows/reusable-copilot-review.yml`

---

## 🔄 Continuous Improvement

### When to Create a New Lesson

**Create lesson when:**

- Issue requires >2 PRs to fully resolve
- Pattern recurs across multiple repos
- Root cause analysis reveals systemic issue
- Solution is non-obvious/counter-intuitive

**Template:**

```markdown
# Lesson #XX (Short Descriptive Title)

**Category:** [Critical/Process/Meta/Advanced/Recent]
**Priority:** [CRITICAL/HIGH/MEDIUM]
**Status:** [✅ Fixed/Implemented/Documented]
**Date:** YYYY-MM-DD
**Repository:** [repo-name]

## Problem

[What went wrong and why]

## Solution

[How it was fixed]

## Action for Future Repos

[Copy-paste implementation steps]

## Related Lessons

[Cross-references]
```

### Lesson Maintenance

**When updating lessons:**

1. Update "Last Updated" date
2. Add cross-references to new related lessons
3. Update statistics in `docs/lessons/README.md`
4. Mark as deprecated if superseded (keep for history)

### This Document Maintenance

**Update copilot-instructions.md when:**

- New critical lesson learned (Priority: CRITICAL/HIGH)
- Workflow changes affect all repos
- Success metrics/benchmarks improve
- New repository types added to organization

---

<!-- NOTE: Update these fields when making significant changes to this document -->

**Last Updated:** 2025-10-18
**Version:** 2.3 (Enhanced Review Workflow Clarity)
**Maintained In:** `./copilot-instructions.md`
**Applies To:** All SecPal repositories (.github, contracts, future repos)
**Base Documentation:** `.github/docs/lessons/` (26 lessons)

---

## Quick Start Checklist

**For Copilot Chat/Coding Assistants working in SecPal repos:**

- [ ] Read this entire document (15-20 min)
- [ ] Review Lesson #25 (pre-commit checklist)
- [ ] Review Lesson #23 (review workflow)
- [ ] Review WORKFLOW-THREAD-RESOLUTION.md
- [ ] Understand first vs. subsequent push behavior
- [ ] Know when to use `set -euo pipefail`
- [ ] Know how to search for patterns comprehensively
- [ ] Know how to verify facts before committing
- [ ] Bookmark `.github/docs/lessons/README.md`
- [ ] Ready to achieve 1-cycle PRs like PR 45! 🎯
