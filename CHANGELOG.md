<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Changelog

Chronological log of notable changes to SecPal organization defaults.

**Note:** This repository contains organization-wide configuration and is NOT versioned. For versioned releases, see individual project repositories (`api/`, `frontend/`, `contracts/`).

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
- **Use case:** Essential after backup restoration or setting up new development environments to identify missing programs

**Why this matters:**

- **Multi-repo awareness:** Checks all three SecPal repositories (api, frontend, contracts) with their specific requirements
- **DDEV detection:** Special handling for API repository's DDEV environment (critical difference vs. standard PHP setup)
- **Local dependencies validation:** Not just global tools, but also checks if `composer install` / `npm install` were run
- **Zero manual debugging:** Script automatically identifies what's missing instead of trial-and-error with preflight.sh failures

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
