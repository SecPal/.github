<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Changelog

Chronological log of notable changes to SecPal organization defaults.

**Note:** This repository contains organization-wide configuration and is NOT versioned. For versioned releases, see individual project repositories (`api/`, `frontend/`, `contracts/`).

---

## 2025-11-16 - Issue Management Protocol (Critical Rule #6)

**Added:**

- **Critical Rule #6: Issue Management Protocol** - ZERO TOLERANCE enforcement for immediate issue creation
  - MANDATORY: Create GitHub issue immediately when bug/issue found in old code that cannot be fixed now
  - MANDATORY: EPIC + sub-issues structure for ALL features requiring >1 PR (>600 lines, multi-module, >1 day work)
  - Top-level `issue_management` section in `copilot-config.yaml` (200+ lines) with complete protocol, workflows, examples
  - Pre-commit checklist item: "Issue Creation Protocol" validates all findings documented as GitHub issues
  - AI Execution Protocol updated with prominent reminder: "Found bug → CREATE GITHUB ISSUE NOW"
  - Forbidden patterns: "TODO: fix later" without issue reference, "we should fix X" without creating issue
  - Cross-reference to `api/docs/EPIC_WORKFLOW.md` for detailed EPIC/sub-issue guidance

- **Issue Management section in Markdown** - Clear, concise rules added before Critical Rules section
  - Immediate issue creation protocol: 8 scenarios requiring immediate action (bugs, tech debt, coverage gaps, etc.)
  - **Security exception:** Vulnerabilities use SECURITY.md for responsible disclosure, NOT public issues
  - EPIC structure requirements: When to use (4 criteria), how to structure (epic → sub-issues → PRs), PR linking rules
  - GitHub CLI commands for issue/epic/sub-issue creation
  - Real-world example: Issue #50 with 7 sub-issues demonstrating complete workflow

**Changed:**

- **Streamlined `review_automation` section** - Replaced 70-line `issue_management` subsection with concise cross-reference
  - Maintains DRY principle: Single authoritative source for issue management rules
  - Old section duplicated information now in top-level `issue_management` section
  - Reduced review_automation from 180 lines to ~115 lines

- **Pre-Commit Checklist enhanced** - Added "Issue Creation Protocol" item (4 validation points)
  - "All discovered bugs/improvements have GitHub issues?"
  - "No 'TODO: fix later' comments without issue reference?"
  - "Complex features (>1 PR) have EPIC + sub-issues structure?"
  - "All unrelated findings documented as separate issues?"

- **AI Execution Protocol** - Added critical reminder at top: Issue creation now equal priority to TDD and Quality Gates
- **PR Rules section** - Updated unrelated findings guidance: "CREATE GITHUB ISSUE IMMEDIATELY (Critical Rule #6)"

**Documentation:**

- All issue management rules consolidated in single location (`copilot-config.yaml:issue_management`)
- Complete AI workflows: Discovery workflow (assess → create issue) and Feature planning workflow (assess complexity → EPIC or simple issue)
- Examples: Security bug during docs work, test coverage gap during feature implementation, duplication refactoring
- EPIC workflow: 6-step process from epic creation to final PR closing epic
- Cross-references: `api/docs/EPIC_WORKFLOW.md` for detailed guide with Issue #50 real-world example

---

## 2025-11-16 - Core Development Principles Enhancement

**Added:**

- **SOLID Principles:** Added comprehensive SOLID principles to core development guidelines
  - Single Responsibility Principle (SRP): One class/function = one reason to change
  - Open/Closed Principle (OCP): Open for extension, closed for modification
  - Liskov Substitution Principle (LSP): Subtypes must be substitutable for base types
  - Interface Segregation Principle (ISP): Many small interfaces > one large interface
  - Dependency Inversion Principle (DIP): Depend on abstractions, not concretions
  - Documentation added to both `.github/copilot-instructions.md` and `.github/copilot-config.yaml`

- **English-Only Communication Rule:** Clarified language policy for GitHub communication
  - All issues, PRs, comments, and documentation MUST be in English
  - Ensures accessibility for international contributors
  - Exceptions: German legal documents (CLA, licenses) and user-facing i18n translations
  - Added to Pre-Commit Checklist for validation

- **No Literal Quotes Rule:** Added guideline against verbatim code duplication
  - Never copy/paste large code blocks without understanding
  - Reference code by file path and line numbers instead
  - Reduces maintenance burden and prevents confusion
  - Correct approach: "See `src/utils/auth.ts` lines 45-60" vs copying 50 lines

**Changed:**

- **Pre-Commit Checklist (Markdown & YAML):** Updated with new validation items
  - Added SOLID Principles check to both markdown documentation and YAML source of truth
  - Added English Only communication check to both markdown and YAML
  - Added No Literal Quotes check to both markdown and YAML
  - DRY Principle already present, now part of comprehensive development principles
  - YAML `copilot-config.yaml:checklists.pre_commit` is the authoritative source

- **Core Development Principles:** Restructured and expanded
  - DRY (Don't Repeat Yourself) now part of formal development principles
  - Quality Over Speed explicitly documented (removed from Critical Rules to avoid duplication)
  - All principles with validation guidance and examples

- **Critical Rules:** Simplified to avoid duplication
  - Removed "Quality Over Speed" from Critical Rule #6 (now only in Core Development Principles)
  - Renumbered subsequent rules (CHANGELOG Mandatory is now #6 instead of #7)

**Impact:**

- Improved code quality through explicit SOLID adherence
- Better international collaboration with English-only policy
- Reduced code duplication in documentation and comments
- Clearer expectations for all contributors

**Files Modified:**

- `.github/copilot-instructions.md` - Added Core Development Principles section before Critical Rules
- `.github/copilot-config.yaml` - Added `development_principles` section with detailed SOLID, DRY, quality-first, communication, and no-literal-quotes rules

**Related:**

- Addresses maintainer request for explicit SOLID principles documentation
- Complements existing DRY principle from Pre-Commit Checklist
- Aligns with Quality-First philosophy from core rules

---

## 2025-11-15 - Reusable Workflow for Conflict Marker Detection

**Added:**

- **Reusable workflow:** Created `reusable-check-conflict-markers.yml` for organization-wide conflict marker detection
  - Downloads and executes shared `scripts/check-conflict-markers.sh`
  - Supports customizable checkout ref via input parameter
  - Detects Git conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`, `|||||||`
  - Prevents accidental commits of unresolved merge conflicts

**Changed:**

- **Migrated `.github` repository:** Updated local `check-conflict-markers.yml` to use reusable workflow
  - Eliminates code duplication (DRY principle)
  - Single source of truth for conflict detection logic
  - Simplifies maintenance across all repositories

**Impact:**

- All SecPal repositories can now use the shared workflow
- Future improvements benefit all repos automatically
- Consistent conflict detection across the organization

**Migration Path:**

Other repositories (api, frontend, contracts) can migrate by updating their workflows:

```yaml
jobs:
  conflict-markers:
    uses: SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@main
```

**Related:**

- Resolves #176: feat: add merge conflict marker check to shared CI/preflight workflow
- Original implementation: SecPal/frontend#113
- Original issue: SecPal/frontend#96

---

## 2025-11-15 - Code Coverage Integration with Codecov

**Added:**

- **Organization-wide Codecov configuration:** Created `.codecov.yml` with coverage thresholds and policies
  - Global coverage target: 80% for project and patches
  - Precision: 2 decimal places, round down
  - Coverage range: 70-100%
  - Backend flag (`api/`) and Frontend flag (`frontend/`)
  - Comprehensive ignore patterns for tests, configs, build artifacts
  - PR comments enabled with coverage diff and tree view
  - Strict CI enforcement: `if_ci_failed: error`

**Changed:**

- **Documentation updates:**
  - Added Code Coverage section to `CONTRIBUTING.md` with local commands and requirements
  - Updated `copilot-instructions.md` with coverage enforcement rule (#11)
  - Added Codecov badges for backend and frontend to organization README
  - Minimum 80% coverage for new code, 100% for critical paths documented

**Implementation:**

- Part of Epic #189: Implement Code Coverage Tracking with Codecov
- Sub-Issue #190: Organization-Level Codecov Configuration & Documentation
- Enables coverage tracking across `api` and `frontend` repositories
- Coverage visible in Codecov dashboard and PR comments

**Impact:**

- Quality gate completion: Coverage requirements now enforced automatically
- Developers can view coverage locally and in CI
- Branch protection can enforce coverage thresholds (to be configured)

---

## 2025-11-15 - Fix Draft PR Reminder Firing on ready_for_review Event

**Fixed:**

- **Draft PR reminder false trigger:** Modified `draft-pr-reminder.yml` to prevent reminder comments when converting draft PR to "Ready for review"
  - Added explicit action check: `github.event.action == 'opened'` to job condition
  - Previously fired on both `opened` and `ready_for_review` events due to reusable workflow behavior
  - Now only reminds on NEW non-draft PRs, not when draft is converted to ready (intended workflow)
  - Resolves confusing duplicate comments on PRs that correctly started as drafts (e.g., api#158)

**Technical Details:**

- Reusable workflows (`workflow_call`) ignore their own `on:` section and inherit all events from calling workflow
- Calling workflows (`project-automation.yml`) trigger on multiple events: `opened`, `ready_for_review`, `closed`, `converted_to_draft`
- Job condition now checks both draft status AND action type to distinguish between new PR and status changes

**Impact:**

- No more false reminders when following correct draft → ready workflow
- Fix automatically applies to all repositories (api, frontend, contracts) using the reusable workflow
- DRY compliance maintained - single centralized fix

**Documentation:** See `docs/BUGFIX_DRAFT_PR_REMINDER.md` for detailed analysis

---

## 2025-11-14 - Fix Dependabot Auto-Merge Timeouts

**Fixed:**

- **Workflow timeout issue:** Modified `lewagon/wait-on-check-action` step in `reusable-dependabot-auto-merge.yml` to add `allowed-conclusions: success,skipped,neutral` and `continue-on-error: true`, allowing the workflow to proceed even when checks like `license/cla` are skipped or neutral
  - Step previously waited for ALL branch protection checks to reach "success" conclusion, causing 50+ minute timeouts
  - `license/cla` check is marked as required by branch protection but comes from external app and may return "neutral" or be skipped for Dependabot PRs
  - GitHub's native auto-merge (`gh pr merge --auto`) already waits for required checks automatically
  - Resolves timeout issues blocking Dependabot PRs across multiple repositories (frontend#131, #126, #127, #128, #129)

**Impact:**

- Auto-merge workflows now complete successfully instead of timing out after 50+ minutes
- Dependabot PRs can merge automatically as designed across all SecPal repositories

**Related:** PR #184

---

## 2025-11-14 - Fix CodeQL Workflow for Repositories Without JavaScript/TypeScript

**Fixed:**

- **CodeQL false failure:** Modified `codeql.yml` workflow to check for JavaScript/TypeScript file presence before running analysis
  - Added `check-languages` job that scans for `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` files (excluding `node_modules` and `.git`)
  - `analyze` job now only runs when `has-javascript=true`, preventing failures in repositories without JS/TS code
  - Resolves CodeQL failure in `.github` repository which contains only YAML/Markdown/Shell files

**Impact:**

- CodeQL workflow succeeds with skipped analysis for repositories without JavaScript/TypeScript code
- Branch protection checks pass for non-JS/TS repositories (e.g., `.github` org defaults repo)
- No false negatives - repositories with JS/TS code still get full security analysis

**Technical Details:**

- Uses `find` command with file extensions and path exclusions for reliable detection
- Conditional job execution via `needs` and `if` ensures proper GitHub Actions check reporting
- Compatible with branch protection rules expecting "CodeQL" check status

**Related:** Discovered during PR #184 review

---

## 2025-11-11 - ADR-005: RBAC Design Decisions

**Added:**

- **ADR-005:** `docs/adr/20251111-rbac-design-decisions.md` - Formal documentation of three critical RBAC design decisions:
  - **Decision 1:** No System Roles - All roles are equal with unified deletion rules and idempotent seeder recovery
  - **Decision 2:** Direct Permissions - Users can have permissions independent of roles for exceptional access cases
  - **Decision 3:** Temporal Assignments Optional - Permanent by default, temporal only when explicitly needed
- **Updated:** `docs/adr/README.md` - Added ADR-005 and ADR-004 to "Accepted" section, created proper section structure

**Context:**

- These decisions emerged during RBAC Phase 4 planning (Issue SecPal/api#108) and were previously only documented in issue threads
- Formalizing as ADR ensures architectural decisions are permanently recorded and linked for future reference
- Supports Phase 4 implementation where other documentation (#143-145) must reference these decisions

**Related:** Issue SecPal/api#142

---

## 2025-11-09 - System Requirements Check Script

**Added comprehensive system validation script for multi-repo setup:**

- **New script:** `scripts/check-system-requirements.sh` - Validates all required tools and dependencies for development across all SecPal repositories
  - **Global system tools:** Git, Bash, cURL, jq, REUSE, ShellCheck, yamllint, actionlint
  - **Git configuration:** user.name, user.email, GPG commit signing
  - **API repository (Laravel + DDEV):**
    - PHP 8.4+, Composer 2.x
    - DDEV (development environment) with running status check
    - PostgreSQL (via DDEV, no local install needed)
    - Laravel tools: Pest, Pint, PHPStan (checks vendor/ directory)
  - **Frontend repository (React + TypeScript):**
    - Node.js 22.x+, npm/yarn/pnpm
    - Local dependencies: TypeScript, Vite, Vitest, ESLint (checks node_modules/)
  - **Contracts repository (OpenAPI):**
    - Node.js 22.x+, npm
    - @redocly/cli (checks node_modules/)
  - **Optional tools:** GitHub CLI (gh), pre-commit, Docker, Docker Compose
  - **Features:**
    - Colored output (green ✓ / yellow ⚠ / red ✗) for visual clarity
    - Installation hints for each missing tool
    - Repository filter: `--repo=api|frontend|contracts` for targeted checks
    - Exit code 0 if all critical requirements met, 1 otherwise
    - Summary report with counts (OK / Warnings / Critical missing)
- **Documentation:** `docs/scripts/CHECK_SYSTEM_REQUIREMENTS.md` - Complete usage guide with typical scenarios (backup restore, new dev system, CI/CD integration)
- **Use case:** Essential after backup restoration or setting up new development environments to identify missing tools

**Why this matters:**

- **Multi-repo awareness:** Checks all three SecPal repositories (api, frontend, contracts) with their specific requirements
- **DDEV detection:** Special handling for API repository's DDEV environment (critical difference vs. standard PHP setup)
- **Local dependencies validation:** Not just global tools, but also checks if `composer install` / `npm install` were run
- **Zero manual debugging:** Script automatically identifies what's missing instead of trial-and-error with preflight.sh failures

---

## 2025-11-09 - Git Conflict Marker Detection

**Added automated detection for unresolved Git merge conflicts:**

- **New script:** `scripts/check-conflict-markers.sh` - Detects conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in tracked files
  - **Prevents accidental commits** of broken code with unresolved merge conflicts
  - **Checks all text files** using `git ls-files` (excludes binary files and .git directory)
  - **Clear output** showing file names and line numbers of conflicts
  - **Actionable guidance** for resolving detected conflicts
- **CI Integration:** GitHub Actions workflow `check-conflict-markers.yml` runs on all PRs and pushes to main
- **Documentation:** `docs/scripts/CHECK_CONFLICT_MARKERS.md` - Complete usage guide with examples and troubleshooting
- **Exit codes:** 0 = clean, 1 = conflicts detected
- **Use case:** Prevents syntax errors in hooks, source code, and configuration files from reaching the repository

---

## 2025-11-08 - DRY Refactoring: Copilot Instructions & YAML Enhancement

**Major refactoring to eliminate redundancy and improve AI parsing performance:**

**copilot-config.yaml - Comprehensive expansion:**

- **Checklists migrated to YAML (DRY compliance):** All checklists now in `checklists` section with validation commands
  - `pre_commit`: 7 checks (TDD, DRY, Quality, CHANGELOG, Documentation, Preflight, No Bypass)
  - `review_passes`: 4-pass strategy (Comprehensive, Deep Dive, Best Practices, Security Auditor)
  - `post_merge_cleanup`: 5-step mandatory cleanup protocol
  - `validation`: General task validation checklist
  - `copilot_proof_standard`: Quality target for zero AI suggestions
- **Workflow mapping added:** `workflows` section maps events to required checklists (before_commit, before_pr, before_merge, after_merge)
- **Multi-repository structure:** `multi_repo` section documents inheritance rules and repo-specific overrides
  - Base: `.github/` (organization-wide rules)
  - Repos: `api/`, `frontend/`, `contracts/` can override non-critical rules
  - Critical rules ALWAYS apply across all repos (TDD, 1 PR = 1 Topic, Signed Commits, REUSE, Domain Policy, Copilot Review Protocol)
  - Coordination: contracts/ FIRST, then api/frontend in parallel
- **Domain Policy:** `domain_policy` section enforces secpal.app/secpal.dev ONLY (ZERO TOLERANCE)
- **Bot PR Validation:** `bot_pr_validation` section codifies tech stack validation for bot-created PRs
- **Learned Lessons as Policies:** `learned_lessons` section converts retrospectives into machine-readable policies
- **🚨 CRITICAL: Copilot Review Protocol clarified:** `copilot_review.absolute_prohibition` section makes rule ultra-prominent
  - NEVER respond to Copilot comments using GitHub comment tools
  - ONLY resolve via GraphQL mutation after fixing code
  - Commenting creates unwanted bot PRs and notification spam

**copilot-instructions.md - Dramatically compressed (64% reduction):**

- **Line count:** 1019 → 368 lines (target was ≤400 lines, achieved)
- **DRY compliance:** Eliminated ~40% redundancy by referencing YAML as Single Source of Truth
- **Structure:** All checklists, validations, tech stack details now reference `copilot-config.yaml` sections
- **Improved readability:** Cleaner format with tables showing workflow-to-checklist mapping
- **Maintained completeness:** All critical information preserved, just referenced instead of duplicated

**scripts/sync-governance.sh - New automation script:**

- **Purpose:** Sync governance files from `.github/` to other repos (addresses Learned Lesson #3)
- **Files synced:** CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, CODEOWNERS, .editorconfig, .gitattributes, scripts/check-domains.sh
- **Modes:** `sync` (copy files) and `check` (validate only)
- **Integration:** Can be added to preflight.sh for automated validation
- **Why:** Symlinks don't render on GitHub.com, files must be copied for proper display

**Impact:**

- **Parsing performance:** Estimated 3.5x faster for AI (YAML direct access vs. Markdown sequential search)
- **Maintainability:** Changes now made in 1 place (YAML) instead of 5-8 places (eliminated duplication)
- **DRY compliance:** Restored (was violating own principles with ~40% redundancy)
- **AI comprehension:** Clearer structure, unambiguous checklists, machine-readable policies
- **Multi-repo coordination:** Explicit inheritance rules prevent DRY violations across repositories

---

## 2025-11-02 - Allow Tailwind Plus License in Compatibility Check

**`reusable-license-compatibility.yml` - Added LicenseRef-TailwindPlus:**

- Added `LicenseRef-TailwindPlus` to list of AGPL-3.0-compatible licenses
- Catalyst UI Kit (Tailwind Plus) explicitly permits use in open source End Products
- License reference: <https://tailwindcss.com/plus/license>
- Components remain under Tailwind Plus License but usage in AGPL projects is allowed per license terms

---

## 2025-10-31 - Copilot Review Protocol Enhancement

**`copilot-instructions.md` - Added bot PR validation + GraphQL review resolution:**

- **GraphQL Review Resolution:** Clarified review threads MUST be resolved via GraphQL mutation (`resolveReviewThread`), NEVER via regular PR comments
- **Bot PR Validation (Lesson #11):** Added critical validation protocol for bot-created PRs (Copilot, Dependabot)
  - Auto-created PRs with pattern `copilot/sub-pr-*` require validation against tech stack
  - Reject if: redundant (duplicate of merged PR), irrelevant (suggests tech not used), out-of-scope (e.g., Rust when PHP/TS/JS only)
  - Example: Rejected Copilot PRs #155 (.github) and #45 (api) - redundant lockfile excludes + invalid JS/TS suggestions for PHP repo
- **Workflow:** Check branch name → validate tech stack → close with explanation if invalid → full review checklist if valid
- Context: Copilot auto-created PRs after review comments mentioned Cargo.lock (future-proofing suggestion) despite SecPal using no Rust

## 2025-10-28 - GitHub App Authentication Migration

**Project Board Automation migrated to GitHub App:**

- Replaced Fine-grained Personal Access Token with GitHub App authentication
- Created "SecPal" GitHub App (ID: 2196125) with organization-wide installation
- Updated all workflow callers to use `APP_ID` and `APP_PRIVATE_KEY` secrets
- Implemented dynamic token generation using `actions/create-github-app-token@v1`
- Benefits: Auto-rotating tokens, bot identity ("SecPal[bot]"), improved reliability
- Resolved cross-repository API authentication issues
- Affected workflows: `.github/workflows/project-automation-core.yml`, caller workflows in all repos

## 2025-10-23 - Copilot Instructions Optimization

**copilot-instructions.md compressed and enhanced:**

- Compressed from 1,047 lines to 393 lines (62% reduction) for AI efficiency
- Removed Change History section (historical information irrelevant for AI)
- Restructured to terse, constraint-based format (AI-only optimization)
- Added AI Self-Check Protocol with trigger events and validation checklist
- Added Multi-Repo Coordination strategy (contracts → api/frontend)
- Added Breaking Changes Process for actual software repositories
- Added CHANGELOG Maintenance guidelines
- Expanded Critical Rules from 6 to 10 (test coverage, commit signing, documentation, templates)
- Added Database Strategy (PostgreSQL prod, SQLite test, reversible migrations)
- Added API Guidelines (REST, JSON, URL versioning, JWT authentication)
- Enhanced Security section (SECURITY.md reference, response timelines)
- Made Copilot Review mandatory (was "recommended")

## 2025-01-23 - Initial Foundation

### Added

#### Documentation & Governance

- Initial repository structure and governance documentation
- `README.md` with project overview and setup instructions
- `CONTRIBUTING.md` with detailed contribution guidelines
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1)
- `SECURITY.md` with vulnerability disclosure process and security policies
- `LICENSE` files for AGPL-3.0-or-later, CC0-1.0, and MIT
- `copilot-instructions.md` with comprehensive development guidelines (1,218 lines)
  - Core Development Philosophy (6 non-negotiable principles)
  - Versioning & Release Strategy (Semantic Versioning 2.0.0)
  - Licensing Strategy with dependency compatibility matrix
  - Dependency Management strategy (Dependabot configuration)
  - Repository Visibility policy (Public by default)
  - Local vs CI Quality Gate Enforcement (3-stage gates)
  - PR Size & Scope Discipline ("One PR = One Topic" rule)
  - Branch Protection Rules and merge strategy

#### Templates

- Pull Request template with quality checklist and "One PR = One Topic" enforcement
- 5 Issue Templates:
  - Bug Report (structured, severity-based)
  - Feature Request (with priority assessment)
  - Documentation (improvement tracking)
  - Security (responsible disclosure workflow)
  - Config/Infrastructure (build, CI/CD, dependencies)
- Issue template configuration (`.github/ISSUE_TEMPLATE/config.yml`)

#### CI/CD & Automation

- Dependabot configuration for 5 ecosystems:
  - GitHub Actions
  - npm (JavaScript/TypeScript)
  - Composer (PHP)
  - pip (Python)
  - Docker (Container images)
- Daily dependency checks at 04:00 CET
- Auto-update strategy for all version types (patch, minor, major)

#### Quality Standards

- REUSE 3.3 compliance setup with SPDX headers
- Documentation for REUSE.toml (replacing deprecated .reuse/dep5)
- Pre-commit and pre-push hook guidelines
- Comprehensive linting standards (Prettier, Markdownlint, ESLint, PHPStan)

#### Technology Stack Documentation

- Backend: Laravel 12, PHP 8.4, Pest, PHPStan (level: max)
- Frontend: React, Node 22.x, TypeScript (strict), Vite, ESLint, Vitest
- API: OpenAPI 3.1 as single source of truth
- Version Control: Git with signed commits, linear history

### Changed

- Nothing (initial release)

### Security

- Secret scanning enabled with push protection
- Dependabot security updates prioritized
- CodeQL analysis configured (JavaScript/TypeScript only, PHP excluded)
- Branch protection enforced with required status checks
- All repositories public by default (AGPL compliance, transparency)

### Notes

This is the foundational release establishing:

- Project governance and contribution workflows
- Quality gates and testing philosophy (TDD mandatory)
- Licensing strategy (AGPL-3.0-or-later for code, CC0-1.0 for config/docs, MIT for scripts)
- Security-first development practices
- Semantic Versioning commitment starting at 0.0.1

**Development Phase:** This is a 0.x.x release. APIs may change without notice. Breaking changes are allowed in minor version bumps. No backward compatibility guarantees until 1.0.0.

**Open Discussions:**

- [Issue #36](https://github.com/SecPal/.github/issues/36): Dependabot auto-merge implementation strategy
- [Issue #37](https://github.com/SecPal/.github/issues/37): Dependabot check frequency (daily vs weekly)
- [Issue #38](https://github.com/SecPal/.github/issues/38): AGPL-3.0-or-later license strategy review
- [Issue #39](https://github.com/SecPal/.github/issues/39): TDD mandatory policy vs exploration exceptions
