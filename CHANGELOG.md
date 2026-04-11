<!-- SPDX-FileCopyrightText: 2026 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Changelog

Log of notable changes to SecPal organization defaults (newest first).

**Note:** This repository contains organization-wide configuration and is NOT versioned. For versioned releases, see individual project repositories (`api/`, `frontend/`, `contracts/`).

---

## 2026-04-11 - Remove Stale Documentation

**Changed:**

- removed stale one-time artifacts and historical docs: YAML Copilot config experiment note (`docs/YAML_COPILOT_CONFIG_TEST.md`), single-fix compliance report (`docs/RETROACTIVE_COMPLIANCE_FIX_ISSUE187.md`), draft-PR-reminder bugfix note (`docs/BUGFIX_DRAFT_PR_REMINDER.md`), and implementation summaries for already-merged automation work (`IMPLEMENTATION_SUMMARY.md`, `WORKFLOW_REVIEW.md`)

## 2026-04-11 - Add Closed Epic Audit Helper

**Changed:**

- added `scripts/audit-closed-epics.sh` to audit closed Epic issues for stale checklist state, unresolved child issues, and false positives caused by PR references in issue bodies
- added a focused shell regression test and wired it into local preflight so future changes keep the audit helper correctly distinguishing issue links from PR links
- documented the retrospective audit command in the shared Epic workflow guide and scripts reference so maintainers can re-check closed epics before trusting their closure state

## 2026-04-11 - Add Timeouts To Inline Workflow Jobs

**Changed:**

- added explicit `timeout-minutes` values to the remaining inline `.github` workflow jobs so organization automation no longer falls back to GitHub Actions' six-hour default for actionlint, draft PR reminders, license checks, project automation, quality checks, REUSE, and the inline workflow test harness job

## 2026-04-11 - Add OFL-1.1 To License Compatibility Allowlist

**Changed:**

- added OFL-1.1 (SIL Open Font License 1.1) to the compatible licenses list in both the
  reusable and standalone license-compatibility workflows; OFL-1.1 fonts are embeddable in
  AGPL-3.0-or-later projects without conflict

## 2026-04-11 - Add Job Timeouts To Reusable Workflows

**Changed:**

- added explicit `timeout-minutes` values to every previously unbounded job in the reusable GitHub Actions workflows so caller repositories inherit bounded execution instead of GitHub's six-hour default
- added a focused `tests/reusable-workflow-timeouts.sh` regression check and wired it into local preflight so missing reusable workflow timeouts fail before push

## 2026-04-11 - Add changelog Repository To Workspace Inventory

**Changed:**

- added the new `changelog` repository to the shared workspace inventory and contributor setup documentation so contributors know to clone and configure it alongside the other active SecPal repositories
- extended the master `.github/setup-hooks.sh` bootstrap and its regression test to install hooks in `changelog` together with the existing repositories
- refreshed organization workspace documentation and repository listings so contributor setup guidance reflects the current seven-repository SecPal workspace

## 2026-04-11 - Centralize Epic Closure Evidence And CLA Ops Verification

**Changed:**

- added a central `docs/EPIC_WORKFLOW.md` guide in the `.github` repository so epic and sub-issue governance no longer depends on the `api` repository as the documentation source of truth
- strengthened the organization issue templates, markdown Copilot baseline, and machine-readable Copilot config to require explicit parent-epic closure evidence, repo-by-repo acceptance verification, and pre-closure tracking of reopened or deferred follow-up work
- extended CLA setup guidance and maintainer-facing docs to require live verification of the external CLA Assistant allowlist and `cla/check` behavior for automated authors such as `copilot-swe-agent`, reducing the chance of future bot PR blockage being treated as fixed based on documentation alone

## 2026-04-08 - Fix setup-hooks Success Counter Abort

**Fixed:**

- replaced the `((SUCCESS_COUNT++))` arithmetic post-increments in `setup-hooks.sh` with `set -e` safe assignment increments so the workspace hook bootstrap no longer aborts after the first successful repository
- added a focused shell regression test that exercises the happy-path multi-repository bootstrap and verifies the final success summary is reported

## 2026-04-06 - Adopt apk.secpal.app Android Distribution Governance

**Changed:**

- accepted `apk.secpal.app` as the canonical Android artifact and download host in the organization-wide domain policy, machine-readable Copilot governance, and local domain validation script
- documented the split between the technical Android artifact host and the human-facing Android landing surface at `secpal.app/android`
- recorded the single-package Android distribution strategy and the rule that provisioning QR codes must be generated privately inside SecPal with short-lived bootstrap tokens rather than published as public static artifacts

## 2026-04-06 - Strengthen Validation Governance

**Changed:**

- strengthened Required Validation to require same-commit test or validation updates when a fix alters observable behavior, validation rules, or automation logic
- mandated `--body-file` for programmatic PR creation in Issue And PR Discipline to prevent shell escaping issues

## 2026-04-06 - Document Copilot CLA Allowlist Exception

**Changed:**

- documented that Copilot-created pull requests currently use the author account `copilot-swe-agent` and must be allowlisted in CLA Assistant alongside the existing Dependabot bot exceptions so the organization-wide `cla/check` status does not block automated PRs

## 2026-04-04 - Clarify Clean Main Start And Post-Merge Readiness

**Changed:**

- clarified that every new work branch must start from a clean, up-to-date local `main`, including an explicit fast-forward pull before the topic branch is created
- extended the documented post-merge cleanup sequence to cover returning to `main`, pulling with fast-forward only, pruning and deleting merged branches, refreshing Composer or Node dependencies where applicable, and confirming the repository is clean again afterward

## 2026-04-04 - Restore Strict Copilot Governance Clarity

**Changed:**

- restored explicit always-on Copilot governance in the central `.github/copilot-instructions.md`, reinstating unambiguous TDD-first, quality-first, one-topic-per-PR, immediate issue-creation, and EPIC-plus-sub-issue rules after the earlier context-bloat reduction made them too implicit at runtime
- tightened `.github/copilot-config.yaml` validation with explicit KISS, YAGNI, one-topic, issue-management, and quality-first emphasis so the central source of truth is stricter than before the rollback
- clarified the PR lifecycle so finished work must be self-reviewed, committed, and pushed before any PR exists, and the first PR state must always be draft until the final PR-view self-review is clean

## 2026-04-03 - Document Local actionlint Remediation For Preflight Warnings

**Changed:**

- made the local `scripts/preflight.sh` warning for missing `actionlint` explicitly point maintainers to `pre-commit run actionlint --all-files` and an optional standalone install path via `go install github.com/rhysd/actionlint/cmd/actionlint@latest`
- extended `setup-hooks.sh`, `WORKSPACE_SETUP.md`, and system-requirements guidance so workspace bootstrap now explains that workflow linting already works through pre-commit hooks and CI even when the standalone `actionlint` binary is absent

## 2026-04-03 - Rename Android Identifier To app.secpal

**Changed:**

- updated the organization-wide Android identifier baseline to `app.secpal`, removed the old identifier exception from current governance text and Copilot configuration, and tightened the shared domain-check allowlist so legacy former host-style strings are no longer implicitly accepted

## 2026-04-01 - Fix Cross-Repo Composite Action Resolution In Reusable Workflows

**Fixed:**

- inlined the Node.js setup and dependency-install steps back into `reusable-prettier.yml` and `reusable-openapi-lint.yml` to restore cross-repo compatibility; GitHub Actions cannot resolve composite actions stored under `.github/actions/` in an external repository when referenced from a step inside a reusable `workflow_call` workflow, causing all callers (`frontend`, `secpal.app`) to fail with "Can't find action.yml"
- the composite action `setup-node-with-deps` is retained for potential future use once a supported path layout is confirmed

## 2026-04-01 - Refactor Reusable Node Workflow Setup

**Changed:**

- extracted the duplicated Node setup and dependency-install logic from the reusable Prettier and OpenAPI lint workflows into a shared composite action
- added explicit lockfile handling for those reusable workflows so missing `package-lock.json` now warns and falls back to `npm install` by default, with an opt-in `require-lockfile` mode for stricter callers
- aligned the touched reusable workflows with current governance expectations by adding explicit `contents: read` permissions and job timeouts

## 2026-04-01 - Tighten Local Tooling Guidance And Workspace Hook Coverage

**Changed:**

- clarified that local `scripts/preflight.sh` does not invoke `actionlint` directly, while workflow linting remains enforced through pre-commit hooks and CI, and documented the optional manual local `actionlint` path consistently across contributor docs
- extended the master `setup-hooks.sh` workspace bootstrap to include the active `android` and `secpal.app` repositories and refreshed the workspace setup guide to match the current six-repository layout

## 2026-04-01 - Adversarial Security Review Second Pass

**Added:**

- completed second-pass adversarial security audit targeting subtle, non-obvious vulnerabilities overlooked in standard reviews
- identified 14 substantive findings (3 critical, 5 high, 6 medium severity) including Merkle tree cryptography weakness, race conditions, and contract/implementation misalignment
- documented findings in `docs/audits/2026-03-31-adversarial-review.md` with exact code references and remediation guidance

## 2026-04-01 - Reduce Copilot Instruction Context Bloat

**Changed:**

- replaced the oversized organization-level Copilot runtime instructions with a shorter self-contained baseline and removed dead `copilot-config.yaml` references that no longer resolve in this repository
- tightened the guidance to the rules that actually need to stay always-on so multi-repo VS Code workspaces send less redundant governance text with each Copilot request
- updated `validate-copilot-instructions.sh` runtime-model checks to accept the new condensed phrasing alongside the original wording

## 2026-03-29 - Align Cross-Repo Domain Policy With Active .dev Hosts

**Changed:**

- corrected the organization-wide domain policy text so `secpal.app` is limited to the public homepage and real email addresses, while `api.secpal.dev` and `app.secpal.dev` are the active API/PWA hosts and the Android application identifier remains Android-only
- updated the shared `check-domains.sh` guidance to flag deprecated `.app` web-host usage separately from valid Android identifier references
- refreshed historical ADR and feature-requirement examples that still used legacy `.app`-style SecPal subdomains as active tenant or employee web-host examples

## 2026-03-22 - Refresh Governance Baseline Docs For Live Repository State

**Changed:**

- Added the `github-actions` automation label to the organization label standard and label sync script
- Updated the GHAS baseline guide to document the live required defaults for `allow_auto_merge`, secret scanning, push protection, Dependabot security updates, and the Copilot review ruleset
- Replaced stale "planned repository" language in the GHAS guide with the current repository classes and added repeatable audit commands for checking live repository settings

**Why:**

The cross-repository governance drift report in Issue #254 was partly based on an older snapshot. The `.github` source documents should describe the current baseline clearly enough that future audits and label sync runs measure the intended state instead of outdated assumptions.

**Impact:**

- Label sync now includes the `github-actions` label expected by Dependabot configurations
- Security baseline guidance now matches the live SecPal repository fleet instead of October 2025 rollout assumptions
- Future governance audits can verify current settings with documented CLI commands instead of relying on stale issue text

## 2026-03-22 - Remove Stale DDEV Assumptions From Governance Docs

**Changed:**

- Replaced DDEV-specific API coverage commands in `CONTRIBUTING.md` with direct `php artisan test` examples
- Updated the system requirements guide and helper script to describe the API runtime as native PHP, remove DDEV as a requirement, and add SSH-friendly guidance for remote execution

**Why:**

Issue #255 correctly identified that organization-level docs and helper scripts were still steering contributors toward a DDEV workflow that no longer matches the active API runtime.

**Impact:**

- Contributors and agents now see API setup guidance that matches the direct shell and SSH-based workflow used by the current Laravel runtime
- The system requirements script no longer reports DDEV as a mandatory API dependency
- Coverage and troubleshooting examples no longer suggest DDEV-only commands

## 2026-03-22 - Enforce Branch Hygiene Before Local Work Starts

**Changed:**

- Added an explicit pre-work branch hygiene workflow to the organization-level Copilot YAML and markdown instructions
- Defined that AI must inspect `git status --short --branch` before edits, never start implementation on local `main`, and stop when an existing non-`main` branch already contains unrelated uncommitted changes
- Added explicit SPDX year-maintenance guidance so edited files and license sidecars keep `SPDX-FileCopyrightText` at the current calendar year using `YYYY` or `YYYY-YYYY` without spaces as appropriate
- Clarified that files without inline SPDX headers must use their companion `.license` files for the same year-maintenance rule
- Added explicit warning-triage guidance so non-fatal diagnostics, audit findings, and deprecation notices must be reviewed and either fixed or tracked immediately

**Why:**

Branch protection on `main` only helps at merge and push time. It does not prevent local mixed work if an agent starts editing on `main` first and creates a topic branch only after hitting protection.

**Impact:**

- Agents now have a documented start-of-work rule instead of relying on branch protection alone
- Dirty non-`main` branches must be assessed before new work continues, which reduces accidental mixed commits across topics
- Edited governance files are less likely to keep stale copyright years after routine maintenance
- Non-fatal tool warnings are less likely to be ignored just because a script still exits successfully

## 2026-03-20 - Replace DDEV Runtime Assumptions In Copilot Guidance

**Changed:**

- Updated organization-level Copilot instructions and YAML guidance to describe the API backend as a native PHP runtime instead of a DDEV-only environment
- Replaced DDEV-specific command examples in the machine-readable backend guidance with direct shell, SSH, and log access guidance that fits the current VPS workflow

**Why:**

SecPal API development now runs directly on the VPS in a full server environment. Organization guidance should not keep telling agents to use container wrappers that are no longer part of the active workflow.

**Impact:**

- Cross-repo AI guidance now matches the real backend runtime and command surface
- Agents are less likely to suggest `ddev exec`, `ddev ssh`, or DDEV-only tooling when operating on the API repository remotely

## 2026-03-19 - Align Laravel Version References With Current Runtime

**Changed:**

- Updated organization-level backend stack references from Laravel 12 to Laravel 13 in the active Copilot guidance and changelog narrative
- Updated `copilot-config.yaml:stack.backend.framework_version` from `12.x` to `13.x` (YAML Single Source of Truth)
- Updated Laravel authorization doc link in `docs/adr/20251108-rbac-spatie-temporal-extension.md` from `12.x` to `13.x`

**Why:**

The API runtime has already been upgraded to Laravel 13, so organization and repository guidance should not continue advertising the old framework baseline.

**Impact:**

- Cross-repo guidance now matches the current Laravel baseline
- `copilot-config.yaml` (machine-readable YAML, primary source for AI tooling) now consistently reflects Laravel 13
- Future repo maintenance is less likely to reintroduce stale Laravel 12 wording into active documentation

## 2026-03-15 - Refresh Stale Product Examples In Development Principles

**Changed:**

- Replaced deleted feature-specific controller, component, hook, and fail-fast examples in `docs/development-principles.md` with current customer-oriented examples

**Why:**

The organization guidance should not teach patterns using a product feature that has already been removed from the active SecPal repositories.

**Impact:**

- Documentation examples now match the current product direction
- New contributors are less likely to reintroduce deleted feature vocabulary into fresh code

## 2026-03-08 - Automate Copilot Review Memory

**Added:**

- **`scripts/copilot-review-tool.sh`** - CLI automation for the Copilot review workflow
  - Fetches Copilot review threads from a PR via GraphQL
  - Exports thread reports in Markdown or JSON
  - Generates durable lessons artifacts that can outlive a single chat session
  - Scans open non-draft PRs across multiple SecPal repositories in one run
  - Aggregates machine-readable finding exports into recurring categories and syncs durable tracking issues
  - Resolves review threads via GraphQL without using comment replies
  - Validates CLI arguments, supports `--max-prs`, and warns when GitHub pagination truncates exports
- **`docs/copilot-review-automation.md`** - operational guide for using review artifacts as durable memory and promoting repeated findings into instructions, hooks, lint rules, tests, and CI
- **`.github/workflows/copilot-review-memory.yml`** - scheduled artifact export for unresolved Copilot findings across `api`, `frontend`, `contracts`, and `.github`
- **`package.json` scripts** for `copilot:review:threads`, `copilot:review:lessons`, `copilot:review:scan`, `copilot:review:resolve`, and `copilot:review:track`
- Persistent category-tracking issues in `SecPal/.github` once recurring findings cross the configured threshold
- Scheduled organization-level workflow runs that export unresolved Copilot findings as workflow artifacts
- Package metadata and lockfile names were aligned for consistent `npm` behavior

**Why:**

Private agent memory cannot be written safely from repository automation.
The maintainable alternative is to automate the durable parts of the process:
capture review findings, turn them into persistent lessons, and promote repeated issues into deterministic guardrails.

**Impact:**

- Copilot review handling no longer depends on manual GraphQL one-offs
- Lessons learned can be persisted as repo-owned artifacts instead of vanishing with a session
- Repeated Copilot findings can be converted into enforceable rules faster
- Recurring review categories now survive PR closure through durable tracking issues
- Open PRs can be scanned automatically on a schedule instead of relying on manual execution
- Scheduled runs generate less artifact noise while still keeping review exports available when findings exist

## 2026-03-08 - Fix Copilot Instruction Validator For Runtime Model

**Fixed:**

- **`scripts/validate-copilot-instructions.sh`** now validates the current self-contained runtime model instead of obsolete `@EXTENDS` and org-reminder assumptions
- Added checks for runtime-model wording, active-instruction frontmatter, and pseudo-inheritance marker removal

**Why:**

The validator still enforced the old pseudo-inheritance approach even though the active repositories now rely on repo-local, self-contained instruction files.

**Impact:**

- Local and CI validation now match the actual Copilot instruction architecture
- False positives from outdated `@EXTENDS` and org-reminder checks are removed

## 2026-03-08 - Harden Copilot Instructions for Multi-Repo Workspace

**Changed:**

- **Clarified** `.github/copilot-instructions.md` runtime semantics — this file is authoritative only inside the `.github` repository itself and does not automatically inherit into sibling repos.
- **Scoped** `.github/instructions/github-workflows.instructions.md` to GitHub automation files only with `applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml,.github/dependabot.yml,.github/dependabot.yaml"`.
- **Aligned companion repo layouts** in `api/`, `frontend/`, and `contracts/` to use self-contained `.github/copilot-instructions.md` files plus targeted `.github/instructions/*.instructions.md` overlays.

**Why:**

VS Code Copilot only loads `.instructions.md` files from the **active workspace root**.
Since `SecPal/.github` is a separate git repo opened as its own workspace folder, sibling
repository rules are not inherited at runtime. Self-contained repo-local instruction files
are the reliable way to keep organization principles and repository-specific guidance active.

**Impact:**

- No more reliance on comment-based pseudo-inheritance across repositories
- Repo-local instruction baselines are explicit and predictable in `api/`, `frontend/`, and `contracts/`
- Workflow rules now activate only for workflow and Dependabot files instead of all YAML files

---

## 2025-11-23 - Fix Dependabot Auto-Merge Job Timeout

**Fixed:**

- **Job timeout issue:** Added `timeout-minutes: 20` to the `auto-merge` job in `reusable-dependabot-auto-merge.yml` to prevent workflows from hanging indefinitely
  - Workflows were waiting unboundedly even when all CI checks had already completed
  - Job now fails after 20 minutes instead of running indefinitely
  - Works in conjunction with existing `continue-on-error: true` on the wait step (added 2025-11-14)
  - Resolves hanging workflows in SecPal/api#238 and SecPal/api#239

**Impact:**

- Dependabot auto-merge workflows complete within reasonable timeframe
- Failed workflows provide clear timeout signal instead of appearing stuck
- Aligns with GitHub Actions best practices for job-level timeout enforcement

---

## 2025-11-23 - Design Principles Consolidation (DRY Compliance)

**Added:**

- **`docs/development-principles.md`** - Human-readable guide for all development principles
  - Comprehensive documentation with code examples (TypeScript + Laravel)
  - Covers all 16 principles: 5 Essential Development Principles (Quality First, TDD, DRY, Clean Before Quick, Self Review Before Push), 5 SOLID Principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion), 3 Additional Design Principles (KISS, YAGNI, Separation of Concerns), and 3 Security & Best Practices (Fail Fast, Security by Design, Convention over Configuration)
  - Clearly marked as human-readable version with reference to YAML as source of truth
  - Framework-specific guidelines for Laravel and React/TypeScript
  - Practical application checklists

**Changed:**

- **`.github/copilot-config.yaml`** - Extended AI source of truth with additional principles
  - Added `kiss`: Keep It Simple, Stupid principle
  - Added `yagni`: You Aren't Gonna Need It principle
  - Added `separation_of_concerns`: Controller → Service → Repository pattern
  - Added `fail_fast`: Early error detection and validation
  - Added `security_by_design`: Input validation, no sensitive logging, multi-layer auth
  - Added `convention_over_configuration`: Framework conventions (Laravel, React)
  - All principles with rules, validation, and examples

- **`.github/copilot-instructions.md`** - Updated AI instructions with all principles
  - Added KISS, YAGNI, Separation of Concerns, Fail Fast, Security by Design to Core Principles section
  - Updated Pre-Commit Checklist to include all 16 principles
  - Added reference to `copilot-config.yaml:development_principles` for complete details

**Related Changes:**

- For API repository documentation updates, see SecPal/api#214

**Impact:**

- ✅ **DRY Compliance**: Single source of truth for all development principles
- ✅ **AI Optimized**: YAML for fast parsing, instructions referencing all principles
- ✅ **Human Readable**: Comprehensive markdown guide with examples
- ✅ **Multi-Repo Ready**: Central documentation, repos reference it (no duplication)
- ✅ **Complete Coverage**: All 16 principles documented for both AI and humans
- ✅ **Consistency**: All repos follow same principles via central documentation

**Structure:**

```text
.github/
├── .github/copilot-config.yaml          # 🤖 AI Source of Truth
├── .github/copilot-instructions.md      # 🤖 AI Instructions (updated)
└── docs/development-principles.md       # 👨‍💻 Human Guide (NEW)

api/
├── DEVELOPMENT.md                       # Quick Ref + Link to .github
└── docs/COPILOT_REMINDER_PATTERNS.md    # Links to .github
```

**Related:**

- Addresses #ISSUE (if any)
- Part of ongoing effort to maintain DRY compliance across multi-repo structure
- Complements existing copilot-config.yaml SOLID principles documentation

---

## 2025-11-21 - Fix Codecov Blocking Dependabot PRs

**Fixed:**

- **Codecov blocking Dependabot auto-merge** - Dependabot PRs in `api` and `frontend` were failing codecov checks despite all GitHub Actions passing
  - Root cause: `require_ci_to_pass: true` caused Codecov to wait for CI before reporting status
  - Dependabot PRs use `continue-on-error: true` for codecov upload (security best practice - no token access)
  - Codecov interpreted skipped upload as failed check and blocked PRs
  - Affected PRs: SecPal/api#204, SecPal/frontend#181, SecPal/frontend#182, SecPal/frontend#183, SecPal/frontend#184, SecPal/frontend#185

**Changed:**

- **`.codecov.yml` configuration** - Adjusted to allow Dependabot PRs while maintaining coverage enforcement
  - Set `require_ci_to_pass: false` - Codecov won't wait for CI checks before reporting
  - Set `wait_for_ci: false` - Don't wait for all CI to complete
  - Kept `informational: false` - Coverage remains **REQUIRED** for normal developer PRs
  - Kept `if_ci_failed: error` - Accurate coverage failure reporting

- **Branch Protection Rules** - Removed `codecov/patch` from required status checks via GitHub API
  - Applied to `SecPal/api` and `SecPal/frontend` repositories
  - Codecov still runs and reports, but doesn't block PRs when no data is uploaded
  - ✅ Applied manually via `gh api` commands (script provided as reference: `scripts/configure-codecov-optional.sh`)

**Impact:**

- ✅ Dependabot PRs can auto-merge: No codecov upload (continue-on-error) + codecov not required = no blocking
- ✅ Coverage enforcement **MAINTAINED**: Normal PRs still require 80% coverage (informational: false)
- ✅ Developer PRs with <80% coverage will **FAIL** codecov check (as intended)
- ✅ No security compromise: Continues using `continue-on-error` for Dependabot uploads
- ✅ **Automated solution:** Branch protection updated via GitHub API - no manual steps needed

**Technical Details:**

The key insight: `require_ci_to_pass: false` allows Dependabot PRs to proceed when no coverage data is uploaded.

- Normal PRs: Upload succeeds → Coverage calculated → Must meet 80% threshold (informational: false)
- Dependabot PRs: Upload skipped (continue-on-error) → No coverage data → Codecov doesn't block (require_ci_to_pass: false)
- Result: Coverage enforcement for developers, no blocking for Dependabot

**Related Issues:**

- This PR fixes the blocking issue for the following Dependabot PRs:
- SecPal/api#204 (actions/checkout 5→6)
- SecPal/frontend#181 (actions/checkout 5→6)
- SecPal/frontend#182 (vite 7.2.2→7.2.4)
- SecPal/frontend#183 (@vitest/coverage-v8 4.0.10→4.0.12)
- SecPal/frontend#184 (@vitest/ui 4.0.10→4.0.12)
- SecPal/frontend#185 (vitest 4.0.10→4.0.12)

**Note:** This PR does NOT close the above issues. They will auto-merge once this configuration is deployed.

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
  - Cross-reference to `api/docs/EPIC_WORKFLOW.md` for detailed EPIC/sub-issue guidance (superseded by `docs/EPIC_WORKFLOW.md` in this repository)

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
- Cross-references: `api/docs/EPIC_WORKFLOW.md` for detailed guide with Issue #50 real-world example (superseded by `docs/EPIC_WORKFLOW.md` in this repository)

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

**Documentation:** `docs/BUGFIX_DRAFT_PR_REMINDER.md` (removed — historical reference only)

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
- **Domain Policy:** `domain_policy` section enforces the approved SecPal host split and rejects deprecated `.app` web-host usage (ZERO TOLERANCE)
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
