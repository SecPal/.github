<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Copilot Instructions (Organization-wide)

> **Scope:** This file applies to **all SecPal repositories** as organization-level default.
> Individual repositories can override by creating their own `.github/copilot-instructions.md`.

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

## Build & Test Commands

### PHP/Laravel Backend

```bash
# Dependencies
composer install --no-interaction --no-progress --prefer-dist --optimize-autoloader

# Code Style Check
./vendor/bin/pint --test

# Static Analysis
./vendor/bin/phpstan analyse --level=max

# Tests (parallel)
php artisan test --parallel
```

### Node.js/React Frontend

```bash
# Dependencies (use exact versions)
npm ci
# or for pnpm projects:
pnpm install --frozen-lockfile

# Linting
npm run lint

# Type Checking
npm run typecheck
# or:
npx tsc --noEmit

# Tests
npm test
# or:
pnpm test
```

### OpenAPI Validation

```bash
# Lint OpenAPI spec
npx @stoplight/spectral-cli lint docs/openapi.yaml
```

### Code Formatting (all files)

```bash
# Check formatting
npx prettier --check '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'

# Auto-fix
npx prettier --write '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'
```

### REUSE Compliance

```bash
# Install REUSE tool
pip install reuse

# Validate compliance
reuse lint

# Add missing headers
reuse annotate --copyright "SecPal" --license "AGPL-3.0-or-later" <file>
```

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

```
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

1. Request new Copilot review via GitHub UI
2. Wait for workflow to re-run and turn GREEN
3. Do NOT merge until check passes

## PR Size & Scope Discipline

### Size Limit: 600 Lines Maximum

**Rationale:** Based on PR history analysis:

- PR #7: 840 lines (too large, hard to review)
- PR #8: 237 lines (good size)
- PR #9: 240 lines (good size, 9 iterations but manageable)

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

### Test-Driven Approach

1. **Write failing test first** (if feature/fix)
2. **Implement minimal fix** to pass test
3. **Refactor** if needed
4. **Verify** all tests still pass

### Code Change Format

- Provide inline diff blocks
- **Maximum 300 lines per diff block**
- Include 3-5 lines context before/after changes
- Use exact file paths (absolute when possible)
- Verify changes compile/run before committing

### Risk Assessment

For non-trivial changes, document:

- **Risks:** What could break?
- **Alternatives:** Other approaches considered?
- **Rollback:** How to undo if needed?
- **Testing:** What scenarios are covered?

### Security & Compliance

**Never include in prompts/logs:**

- API keys, tokens, passwords
- Database credentials
- Private keys or certificates
- User PII or sensitive data

**Always verify:**

- SPDX headers on new files
- License compatibility for new dependencies
- No hardcoded secrets in code

### Draft → Ready Workflow

1. Create PR as **Draft**
2. Run all automated checks locally
3. Fix issues until all GREEN
4. Push and verify CI passes
5. Request Copilot review
6. Address feedback
7. Mark as **Ready for review** only when:
   - ✅ All checks GREEN
   - ✅ Fresh Copilot review
   - ✅ All threads resolved

## OpenAPI Conventions

### Single Source of Truth

`docs/openapi.yaml` defines the contract. Backend and frontend must conform.

### Consistency Requirements

- **Error Responses:** Use standard `application/problem+json` format
- **Pagination:** Cursor-based with `meta.next_cursor`
- **Authentication:** OAuth2 Bearer tokens
- **Versioning:** URI versioning (`/api/v1/...`)
- **Caching:** Use `ETag` + `If-None-Match` headers
- **Rate Limiting:** Standard headers (`X-RateLimit-*`)

### Validation

OpenAPI changes must:

1. Pass Spectral linting
2. Remain backward-compatible (for existing endpoints)
3. Include example requests/responses
4. Document all status codes

## Workflow Architecture

### Reusable Workflows

All quality checks are defined as reusable workflows in `SecPal/.github`.

**Available for all SecPal repositories:**

- `reusable-reuse.yml` - REUSE compliance
- `reusable-license-compatibility.yml` - License checks
- `reusable-prettier.yml` - Code formatting
- `reusable-markdown-lint.yml` - Markdown linting
- `reusable-actionlint.yml` - Workflow linting
- `reusable-php-lint.yml` - Laravel Pint
- `reusable-php-stan.yml` - PHPStan analysis
- `reusable-php-test.yml` - Pest tests
- `reusable-node-lint.yml` - ESLint
- `reusable-node-test.yml` - Vitest tests
- `reusable-node-build.yml` - Vite build
- `reusable-openapi-lint.yml` - Spectral validation
- `reusable-copilot-review-check.yml` - Review freshness check

**See:** `.github/workflows/README.md` for detailed usage and parameters.

### Usage in Other SecPal Repos

Each repository should create `.github/workflows/ci.yml` using the reusable workflows.

**Example for `SecPal/backend`:**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  # Quality checks
  reuse:
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@main

  prettier:
    uses: SecPal/.github/.github/workflows/reusable-prettier.yml@main

  # Backend checks
  pint:
    uses: SecPal/.github/.github/workflows/reusable-php-lint.yml@main

  phpstan:
    uses: SecPal/.github/.github/workflows/reusable-php-stan.yml@main

  pest:
    uses: SecPal/.github/.github/workflows/reusable-php-test.yml@main

  # Quality gate (runs after code checks)
  copilot-review:
    uses: SecPal/.github/.github/workflows/reusable-copilot-review-check.yml@main
```

## Branch Protection Rules

Configure these settings in repository settings:

### Required Status Checks

Add as required before merge:

- `Check Code Formatting`
- `Check REUSE Compliance`
- `Check License Compatibility`
- Backend: `Pint`, `PHPStan`, `Pest`
- Frontend: `ESLint`, `TypeCheck`, `Vitest`
- `Verify Copilot Review` ⭐ (enforces fresh review)

### Branch Rules

- ✅ Require signed commits
- ✅ Require linear history
- ✅ Require conversation resolution
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

**After 3 iterations:**

1. Pause and reassess scope
2. Consider splitting PR
3. Document blockers in PR comment
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

### Before Merging

- ✅ All required checks GREEN
- ✅ Fresh Copilot review (auto-verified by workflow)
- ✅ All conversations resolved
- ✅ PR description clear and complete
- ✅ Squash commits into single logical commit

## Contact & Escalation

For questions or issues with these guidelines:

1. Check PR #9 for context on review enforcement
2. Review workflow documentation in `.github/workflows/README.md`
3. Consult Git history for examples of good PRs (#8, #9)

---

**Last Updated:** 2025-10-19 (based on PRs #7-9 learnings)
