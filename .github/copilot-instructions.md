<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Instructions (Organization-wide)

> **Scope:** This file applies to **all SecPal repositories** as organization-level default.
> Individual repositories can override by creating their own `.github/copilot-instructions.md`.
>
> **Note:** This foundational document exceeds the typical 600-line PR limit (see "PR Size & Scope Discipline" section).
> As comprehensive instructions that establish organization-wide standards, the larger size is justified for completeness and long-term reference value.

This document provides context and guidance for GitHub Copilot (Chat, Agent, Code Reviews) to ensure efficient, high-quality development while avoiding endless iteration loops.

## Repository Structure

SecPal is organized as **multiple repositories** under the `SecPal` organization:

- **`SecPal/.github`** - Organization defaults (this repo): workflows, templates, shared configs
- **`SecPal/backend`** - Laravel API backend (planned)
- **`SecPal/frontend`** - React frontend (planned)
- **`SecPal/docs`** - Documentation & OpenAPI specs (planned)
- _(additional repos as needed)_

Each repository follows the standards defined here unless explicitly overridden.

## Project & Tech Stack

### Backend: Laravel (PHP)

- **PHP Version:** 8.4
- **Framework:** Laravel 12
- **Testing:** Pest/PHPUnit with parallel execution
- **Static Analysis:** PHPStan/Larastan (level: max)
- **Code Style:** Laravel Pint

### Frontend: React + TypeScript

- **Node Version:** 22.x
- **Build Tool:** Vite
- **Language:** TypeScript (strict mode)
- **Linting:** ESLint
- **Testing:** Vitest + React Testing Library

### API Contracts

- **Format:** OpenAPI 3.1
- **Location:** `docs/openapi.yaml`
- **Single Source of Truth:** API contract drives both backend and frontend

### Infrastructure

- **License:** AGPL-3.0-or-later (all code)
- **Compliance:** REUSE 3.3 (SPDX headers required)
- **Version Control:** Git with signed commits, linear history
- **CI/CD:** GitHub Actions with reusable workflows

### Code Security Scanning

- **Tool:** CodeQL (GitHub Advanced Security)
- **Supported Languages:**
  - ✅ JavaScript/TypeScript, Python, Java, Go, C/C++, C#, Ruby, Swift
  - ❌ **PHP is NOT supported by CodeQL** - use other tools (PHPStan, Psalm, Semgrep)
- **Configuration:** `.github/workflows/codeql.yml`
- **Note:** Always verify language support before adding to CodeQL matrix
- **Reference:** [CodeQL language support documentation](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)

### Quality Standards

- **REUSE 3.3:** All files must have SPDX headers
- **Code Style:** Prettier (Markdown, YAML, JSON, TS, JS)
- **Linting:** Language-specific linters (PHPStan, ESLint)
- **Testing:** Automated tests required, must pass
- **Markdown:** `markdownlint`, `prettier`
- **Shell Scripts:** `shellcheck`
- **GitHub Actions:** `actionlint`

> **See:** [README.md](../README.md) for detailed build & test commands (PHP, Node.js, OpenAPI, REUSE).

## PR Gates & Workflow Order

**CRITICAL: Gates must pass in this exact order to avoid wasted cycles.**

### 1. Pre-Merge Automated Checks (Must be GREEN first)

Run **before** requesting Copilot review:

1. **Code Formatting** (`prettier`)
2. **REUSE Compliance** (`reuse lint`)
3. **License Compatibility** (all dependencies AGPL-compatible)
4. **Markdown Lint** (`markdownlint`)
5. **Workflow Lint** (`actionlint`)
6. **Backend:**
   - Laravel Pint (code style)
   - PHPStan (static analysis)
   - Pest (tests)
7. **Frontend:**
   - ESLint
   - TypeScript (`tsc --noEmit`)
   - Vitest (tests)
8. **API:**
   - Spectral (OpenAPI validation)

### 2. Copilot Code Review (Quality Gate)

**Only after all automated checks are GREEN:**

- Request Copilot review via GitHub UI
- Wait for review to complete
- Address all feedback
- Re-request if changes are made

### 3. Ready for Review Status

**Only set to "Ready for review" when:**

- ✅ All automated checks GREEN
- ✅ Copilot review completed and up-to-date
- ✅ All review threads resolved
- ✅ PR size ≤ 600 lines

## Fresh-after-HEAD Rule

**Prevents stale reviews from being merged.**

### Definition

A Copilot review is **fresh** if:

```text
review.submitted_at > commit.committer.date (of HEAD commit)
```

### Enforcement

The `copilot-review-check.yml` workflow verifies:

1. At least one review exists from `copilot-pull-request-reviewer[bot]`
2. Review `submitted_at` timestamp is **after** the latest commit timestamp
3. Fails check if review is missing or outdated

### When Review Becomes Stale

Review becomes stale when:

- New commits are pushed after the last review
- Code is amended/rebased
- Any changes to PR branch

### Action Required

If review is stale:

1. Request new Copilot review:
   - **Via GitHub UI:** PR page → Reviews section → Request review from Copilot
   - **Via GitHub API:** Use the MCP GitHub tool or `gh api` to request review
   - ⚠️ **Note:** `gh pr review --copilot` does NOT exist in gh CLI
2. Wait for workflow to re-run and turn GREEN
3. Do NOT merge until check passes

## PR Size & Scope Discipline

### Size Limit: 600 Lines Maximum

**Rationale:** Based on PR history analysis:

- **PR #7** (reusable workflows): 840 lines - too large, hard to review comprehensively
- **PR #8** (actionlint + pre-commit): 237 lines - optimal size, quick review cycle
- **PR #9** (Copilot review enforcement): 240 lines - optimal size, 9 iterations but manageable due to focused scope

> **Note:** Although PR #9 exceeded the target of ≤3 review iterations per PR (see line 432), the higher count was acceptable because each iteration addressed narrowly scoped feedback, enabling rapid convergence. Exceptions may be warranted for foundational or process-changing PRs.

**Exception:** Documentation and configuration files (like this instructions file) may exceed the limit when establishing foundational standards.

**Target:** Keep PRs ≤ 600 changed lines for maintainability.

### Slice Strategy for Large Changes

If change exceeds 600 lines, split into ≤ 3 sequential PRs:

1. **PR 1:** Infrastructure/types/interfaces
2. **PR 2:** Core implementation
3. **PR 3:** Tests and documentation

### One PR = One Change Class

**Prohibited combinations in single PR:**

- ❌ Feature + Refactor
- ❌ Fix + Documentation
- ❌ Lint + Logic changes
- ❌ Multiple unrelated features

**Allowed single-class PRs:**

- ✅ New feature (implementation + tests + docs)
- ✅ Bug fix (fix + regression test)
- ✅ Refactor (pure refactor + updated tests)
- ✅ Documentation (only docs changes)

## Agent Working Guidelines

### Self-Critique Framework

**Before every change, ask yourself:**

1. **Is it NEW or REDUNDANT?** - Does Copilot/GitHub already know this?
2. **Does it solve a REAL problem?** - Not hypothetical edge cases
3. **Does it make the file BETTER or just LONGER?** - Quality over quantity
4. **Is there a BETTER place for it?** - Separate file? README? Docs?
5. **File size impact?** - Check before/after:
   - ✅ <400 lines: Good
   - ⚠️ 400-600 lines: Consider compression
   - 🔴 >600 lines: MUST split or compress

### Test-Driven Approach

1. **Write failing test first** (if feature/fix)
2. **Implement minimal fix** to pass test
3. **Refactor** if needed
4. **Verify** all tests still pass

### Security & Compliance

**Never include:**

- API keys, tokens, passwords, database credentials
- Private keys, certificates, user PII, sensitive data

**Always verify:**

- SPDX headers on new files
- License compatibility for new dependencies
- No hardcoded secrets in code

## OpenAPI Conventions

### Single Source of Truth

`docs/openapi.yaml` defines the contract. Backend and frontend must conform.

> **See:** Future PR will add `docs/openapi.md` with detailed OpenAPI conventions (naming, structure, validation, error responses, pagination, authentication).
> Future PR will also enhance `.github/workflows/README.md` with workflow architecture and usage examples.

## Branch Protection Rules

Configure these settings in repository settings:

### Required Status Checks

⚠️ **CRITICAL:** Status check names must match **exact job names** from workflow files, NOT workflow names!

**Example mismatch that blocks merging:**

- ❌ Workflow name: "Code Quality" → Branch Protection expects: "Code Quality" → **FAILS** (no such check)
- ✅ Job name: "Check Code Formatting" (from workflow "Code Quality") → **WORKS**

⚠️ **Conditional Required Checks Problem:**

Some checks only run when specific files change (e.g., "Lint GitHub Actions Workflows" only runs on `.github/workflows/*.yml` changes).

**DO NOT mark conditional checks as required** - they will block PRs that don't modify their trigger files (docs-only PRs, etc.).

**Safe required checks** (run on ALL PRs):

- `Check Code Formatting` (from workflow: Code Quality)
- `Check REUSE Compliance` (from workflow: REUSE Compliance)
- `Check License Compatibility` (from workflow: License Compatibility)
- Backend: `Pint`, `PHPStan`, `Pest` (if backend code exists)
- Frontend: `ESLint`, `TypeCheck`, `Vitest` (if frontend code exists)
- `Verify Copilot Review` ⭐ (enforces fresh review)

**Conditional checks** (DO NOT require):

- `Lint GitHub Actions Workflows` - only runs on workflow file changes
- Any path-filtered checks

### Branch Rules

- ✅ Require signed commits
- ✅ Require linear history
- ✅ Require conversation resolution
- ✅ Enforce admins: **true**
  - ⚠️ **Important:** When enabled, even admins cannot bypass required checks with `gh pr merge --admin`
  - All status checks must pass, including "Verify Copilot Review"
  - If checks must be bypassed in emergency situations, document the reason and re-enable this setting immediately after the merge
- ✅ Allow squash merging (preferred)
- ❌ Disable force push (except admins)

## Preventing Endless Loops

### Common Loop Causes & Solutions

| Cause                         | Solution                                         |
| ----------------------------- | ------------------------------------------------ |
| Stale review not detected     | Use `copilot-review-check.yml` workflow          |
| Checks run before review      | Follow gate order: checks → review → ready       |
| Large PRs cause many comments | Keep PRs ≤ 600 lines                             |
| Scope creep during dev        | One PR = one change class                        |
| Format changes trigger CI     | Run `prettier` + `reuse lint` before first push  |
| Review finds preventable bugs | Write tests first, run locally before pushing    |
| Unclear requirements          | Document acceptance criteria in PR description   |
| Edge cases not considered     | Risk assessment for complex changes              |
| Breaking changes              | OpenAPI backward compatibility + versioning      |
| Secrets in code               | Pre-commit hooks + code review for secrets check |

### Iteration Budget

**Target:** ≤ 3 review iterations per PR

> **Note:** While the target is 3 iterations, exceptions may occur for complex or high-impact changes. For example, [PR #9](https://github.com/SecPal/.github/pull/9) required 9 iterations due to extensive review and scope adjustments. In such cases, document the reasons for exceeding the target and follow the escalation steps below.

**After 3 iterations:**

1. Pause and reassess scope
2. Consider splitting PR
3. Document blockers and reasons for extra iterations in PR comment (reference relevant PRs if helpful)
4. Request human review if agent stuck

### Quality vs Speed

**Quality first approach:**

- Run checks locally before push
- Write clear PR descriptions
- Self-review diff before marking ready
- Don't rush to merge

**Signs of rushing:**

- ❌ Marking ready before checks pass
- ❌ Ignoring Copilot feedback
- ❌ Partial fixes ("will fix later")
- ❌ Unclear commit messages

## Quick Reference

### Before Creating PR

```bash
# Format code
npx prettier --write .

# Add SPDX headers
reuse annotate --copyright "SecPal" --license "AGPL-3.0-or-later" <new-files>

# Run checks locally
npm run lint          # or: pnpm lint
npm run typecheck     # or: pnpm typecheck
npm test              # or: pnpm test

# Backend equivalents
./vendor/bin/pint --test
./vendor/bin/phpstan analyse
php artisan test --parallel

# Validate OpenAPI
npx @stoplight/spectral-cli lint docs/openapi.yaml

# REUSE check
reuse lint

# Commit with sign-off
git commit -S -m "feat: add feature X"
```

### During PR Review

1. ✅ All automated checks GREEN?
2. ✅ PR ≤ 600 lines?
3. ✅ One change class only?
4. ✅ Request Copilot review
5. ✅ Address all feedback
6. ✅ Re-request if changes made
7. ✅ All threads resolved?
8. ✅ Fresh review after HEAD?
9. ✅ Mark as "Ready for review"

### Resolving Multiple Review Threads Efficiently

For PRs with many review comments (>5 threads), use GitHub GraphQL API instead of clicking "Resolve" in UI:

**Note:** Replace `REPO_NAME`, `PR_NUMBER` with actual values, and `PRRT_xxxxx` with thread IDs from step 1.

```bash
# 1. Get all review thread IDs
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: "REPO_NAME") {
    pullRequest(number: PR_NUMBER) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              body
            }
          }
        }
      }
    }
  }
}'

# 2. Bulk resolve threads (up to 6 per mutation)
gh api graphql -f query='
mutation {
  t1: resolveReviewThread(input: {threadId: "PRRT_xxxxx1"}) {
    thread { id isResolved }
  }
  t2: resolveReviewThread(input: {threadId: "PRRT_xxxxx2"}) {
    thread { id isResolved }
  }
  t3: resolveReviewThread(input: {threadId: "PRRT_xxxxx3"}) {
    thread { id isResolved }
  }
}
'
```

This is significantly faster than manual UI resolution for many threads.

### Before Merging

- ✅ All required checks GREEN
- ✅ Fresh Copilot review (auto-verified by workflow)
- ✅ All conversations resolved
- ✅ PR description clear and complete
- ✅ Squash commits into single logical commit

### After Merging

Clean up branches and update local repository:

```bash
# Fetch and prune deleted remote branches
git fetch --prune

# Switch to main and update
git checkout main
git pull origin main

# Verify clean state (should only show main branches)
git branch -a

# Optional: Clean up Git database
git gc --prune=now
```

**Note:** `gh pr merge --delete-branch` deletes the remote branch but not the local one. Always run `git fetch --prune` to update local references.

## Contact & Escalation

For questions or issues with these guidelines:

1. Review workflow documentation in `.github/workflows/README.md`
2. Consult Git history for examples of good PRs (#8, #9, #23-25)

---

**Version:** 1.2.0
**Last Updated:** October 22, 2025

**Changes:**

- **Compression:** Reduced from 610 → 475 lines (-135 lines, -22%)
- **Removed:** Build & Test Commands (see README.md), OpenAPI details (future: docs/openapi.md), Workflow Architecture (future: workflows/README.md)
- **Removed:** Redundant Code Change Format, Risk Assessment, Draft→Ready Workflow sections
- **Added:** Self-Critique Framework (file size awareness, quality over quantity)
- **Added:** Conditional Required Checks warning (prevents docs-only PR blocks)
- **Note:** Reference documentation will be added in follow-up PR #27
- **Based on:** PRs #7-9, #23-25 learnings
