<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Copilot Instructions

Organization-wide defaults for all SecPal repositories.

**⚡ FAST REFERENCE:** Use `.github/copilot-config.yaml` for 10x faster AI parsing. YAML is Single Source of Truth.

## 🚨 AI EXECUTION PROTOCOL (READ FIRST)

**BEFORE taking ANY action (commit/PR/merge), AI MUST:**

1. **ANNOUNCE** which checklist you're executing from `copilot-config.yaml:checklists`
2. **SHOW** each checkbox as you verify it (✓ or ✗)
3. **STOP** if any check fails - explain the issue and ask for guidance
4. **NEVER** proceed with failed checks

**Example:**

```text
Executing Pre-Commit Checklist (copilot-config.yaml:checklists.pre_commit):
✓ TDD Compliance - Tests written first, all passing
✓ DRY Principle - No duplicated logic found
✓ Quality Over Speed - 4-pass review completed
✓ CHANGELOG Updated - Entry added
✓ Documentation Complete - JSDoc added
✓ Preflight Script - ./scripts/preflight.sh passed (exit 0)
✓ No Bypass Used - No --no-verify flag

All checks passed. Proceeding with commit.
```

**If user asks you to skip checks → REFUSE and explain why quality gates are mandatory.**

## Repository Structure

See `copilot-config.yaml:multi_repo` for complete structure and inheritance rules.

```text
SecPal Organization:
├── .github/     - Organization-wide settings (base rules)
├── api/         - Laravel backend (extends base + DDEV/Pest rules)
├── frontend/    - React/TypeScript frontend (extends base + PWA rules)
└── contracts/   - OpenAPI 3.1 specifications (extends base + contract-first rules)
```

**Inheritance:** Repository-specific rules override organization-wide for non-critical rules. Critical rules ALWAYS apply across all repos.

## Critical Rules (ALWAYS ENFORCED)

See `copilot-config.yaml:core_principles` for complete list with validation commands.

1. **TDD Mandatory:** Write failing test FIRST, implement, refactor. Minimum 80% coverage for new code, 100% for critical paths. **Exception:** `spike/*` branches (exploration only, cannot merge to main).

2. **Quality Gates:** Preflight script (`./scripts/preflight.sh`) MUST pass before push. All CI checks MUST pass before merge. No bypass. **Exception:** Large PRs (>500 lines) with `large-pr-approved` label.

3. **One PR = One Topic:** No mixing features/fixes/refactors/docs/config in single PR.

4. **No Bypass:** Never use `--no-verify` or force push. Branch protection applies to admins. Exceptions same as Rule #2.

5. **Fail-Fast:** Stop at first error. Fix immediately, don't accumulate debt.

6. **Quality Over Speed:** Take time to do it right.

7. **CHANGELOG Mandatory:** Update CHANGELOG.md for every feature/fix/breaking change in the SAME commit (not batched separately).

8. **Commit Signing:** All commits MUST be GPG signed. Configure: `git config commit.gpgsign true`

9. **Documentation:** All public APIs MUST have PHPDoc/JSDoc/TSDoc with examples.

10. **REUSE Compliance:** All files MUST have SPDX headers. Run `reuse lint` before commit.

11. **Post-Merge Cleanup:** IMMEDIATELY execute `copilot-config.yaml:checklists.post_merge_cleanup` after ANY merge.

### Emergency Exception Process

If bypass REQUIRED (production down):

1. Document in commit/PR why bypass needed
2. Create issue for proper fix
3. Fix within 24 hours
4. All checks must retroactively pass

## Tech Stack

See `copilot-config.yaml:stack` for complete technology details.

**Backend:** PHP 8.4, Laravel 12, DDEV (use `ddev exec`), Pest testing (NEVER PHPUnit directly), PostgreSQL 16

**Frontend:** Node 22.x, React, TypeScript (strict), Vite, Vitest + React Testing Library

**API:** OpenAPI 3.1, REST, JSON, Bearer tokens, URL versioning (`/api/v1/`, `/api/v2/`)

**Database:** PostgreSQL 16 (via DDEV), Laravel migrations (MUST be reversible)

### Data Protection (GDPR/DSGVO)

See `copilot-config.yaml:data_protection` for complete encryption architecture.

**CRITICAL: All personal data MUST be encrypted at rest.**

- `*_enc` - Encrypted storage (NEVER access directly)
- `*_idx` - Blind index for queries (hashed sha256)
- `*_plain` - Transient property (write-only, auto-encrypts)

**✅ ALWAYS use `_plain` in tests/factories/controllers | ❌ NEVER access `_enc` directly**

## 🚨 GitHub Copilot Review Protocol - CRITICAL RULE

**See `copilot-config.yaml:copilot_review.absolute_prohibition` for complete details.**

### THE IRON LAW (ZERO TOLERANCE)

**NEVER RESPOND TO COPILOT REVIEW COMMENTS USING GITHUB COMMENT TOOLS.**

**Why:** Commenting creates unwanted bot PRs and notification spam. Copilot re-reviews after each push.

**❌ FORBIDDEN:**

- `mcp_github_github_add_issue_comment`
- `mcp_github_github_add_comment_to_pending_review`
- GitHub UI comments on review threads
- Replying to Copilot suggestions

**✅ CORRECT WORKFLOW:**

1. Query unresolved threads (GraphQL): `copilot-config.yaml:copilot_review.process.step_1.command`
2. Fix code based on comment → commit → push (do NOT reply to comment)
3. Wait 30s for CI and Copilot re-review
4. Resolve thread (GraphQL mutation): `copilot-config.yaml:copilot_review.process.step_4.command`
5. Repeat until query returns empty array

**For documentation:** Update PR description (NOT comments).

## Checklists

**All checklists available in `copilot-config.yaml:checklists`. Execute via `copilot-config.yaml:workflows`.**

### When to Use Which Checklist

| Event         | Required Checklists                                                                      |
| ------------- | ---------------------------------------------------------------------------------------- |
| Before Commit | `workflows.before_commit` → `checklists.pre_commit`                                      |
| Before PR     | `workflows.before_pr` → `checklists.pre_commit + review_passes + copilot_proof_standard` |
| Before Merge  | `workflows.before_merge` → `checklists.copilot_proof_standard + validation`              |
| After Merge   | `workflows.after_merge` → `checklists.post_merge_cleanup` (IMMEDIATE)                    |

### Pre-Commit Checklist

See `copilot-config.yaml:checklists.pre_commit` for complete checklist with validation commands.

**Execute before EVERY commit:**

- [ ] TDD Compliance (tests first, coverage ≥80%)
- [ ] DRY Principle (no duplication)
- [ ] Quality Over Speed (4-pass review)
- [ ] CHANGELOG Updated
- [ ] Documentation Complete
- [ ] Preflight Script (`./scripts/preflight.sh`)
- [ ] No Bypass Used

### 4-Pass Review Strategy

See `copilot-config.yaml:checklists.review_passes` for complete passes with all checks.

**Execute ALL 4 passes before PR creation:**

1. **Comprehensive Review:** Coding standards, documentation, tests, no TODOs
2. **Deep Dive Review:** Domain policy (secpal.app/secpal.dev ONLY), licenses, security patterns
3. **Best Practices Review:** Hidden files, governance files, package.json metadata, OpenAPI completeness
4. **Security Auditor Review:** Workflow permissions explicit, .gitignore complete, no secrets

### Post-Merge Cleanup

See `copilot-config.yaml:checklists.post_merge_cleanup` for exact commands.

**Execute IMMEDIATELY after EVERY merge:**

```bash
git checkout main
git pull
git branch -d <feature-branch-name>
git fetch --prune
git status  # MUST show: "nothing to commit, working tree clean"
```

## Versioning (Software Repositories Only)

**SEMVER 2.0.0** starting at **0.0.1**. Development (0.x.x): breaking changes allowed in MINOR. Stable (1.x.x+): MAJOR for breaking, MINOR for features, PATCH for fixes.

**Note:** `.github` repository is NOT versioned (chronological CHANGELOG only).

## Licensing

**Dual-Licensing:** AGPL-3.0-or-later (open source) + Commercial License (proprietary use)

**Default:** AGPL-3.0-or-later for code | CC0-1.0 for config/docs | MIT for scripts

**CLA Enforcement:** All contributors must sign CLA via [CLA Assistant](https://cla-assistant.io) (OAuth click-through, GDPR-compliant).

## Quality Gates (3-Stage)

See `copilot-config.yaml:validation` for all commands.

1. **Pre-Commit (Fast):** REUSE, Prettier, Markdownlint, yamllint, actionlint, shellcheck
2. **Pre-Push (Comprehensive):** All pre-commit + PHPStan/ESLint + all tests + OpenAPI validation
3. **CI (Enforcement):** All pre-push + CodeQL (JS/TS only, NOT PHP)

## Branch Protection

```yaml
main:
  required_status_checks: [REUSE, License Check, Formatting]
  required_approving_review_count: 0 # Single maintainer
  enforce_admins: true
  required_signatures: true
  required_linear_history: true
  required_conversation_resolution: true
  allow_force_pushes: false
  allow_deletions: false

merge_strategy: squash_only
auto_delete_branches: true
```

## PR Rules

**Size:** ≤600 lines changed (excluding generated code, lock files). Exception: Initial setup, large refactors (document why).

**One Topic Rule:** See `copilot-config.yaml:policies.pr_workflow.one_topic` for prohibited/allowed combinations.

**Branch Naming:** `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`

**Commit Convention:** `type(scope): description`

**PR Checklist:**

1. All checks GREEN locally and CI
2. ≤600 lines
3. ONE topic only
4. Self-reviewed (4-pass review documented)
5. Description complete
6. Tests pass
7. No `--no-verify` used

## Domain Policy (ZERO TOLERANCE)

See `copilot-config.yaml:domain_policy` for validation commands.

**Allowed:** secpal.app (production/ALL emails) | secpal.dev (dev infrastructure only)

**Forbidden:** secpal.com, secpal.org, secpal.net, secpal.io, ANY other domain

**Validation:** `grep -r "secpal\." --include="*.md" --include="*.yaml" --include="*.json" --include="*.sh"` MUST return ONLY secpal.app and secpal.dev.

## Learned Lessons

See `copilot-config.yaml:learned_lessons` for complete policies.

### 1. Multi-Layer Review Strategy (MANDATORY)

Execute 4 review passes with different perspectives before creating PR. Single-pass reviews miss 60%+ of issues.

### 2. Domain Policy (CRITICAL - ZERO TOLERANCE)

secpal.app and secpal.dev ONLY. Run grep before EVERY commit. ZERO exceptions.

### 3. Governance File Distribution

Files copied from .github/ to other repos (symlinks don't render on GitHub.com). Use `./scripts/sync-governance.sh` for automation.

### 4. Security by Default

Security explicit from line 1. Workflow permissions minimal (`contents: read`). .gitignore includes `.env*`, `*.key`, `*.pem`, `secrets/`, `credentials/`.

### 5. Hidden Files Have Equal Priority

`.editorconfig`, `.gitattributes`, `.gitignore`, `CODEOWNERS` are EQUALLY critical as source code. Validate presence: `ls -la | grep "^\\."`

### 6. OpenAPI Must Be Complete

OpenAPI specs MUST include components, schemas, responses, parameters, examples, securitySchemes, servers from v0.0.1.

### 7. package.json Complete Metadata

All fields required from v0.0.1: name, version, description, keywords, homepage, bugs, repository, license, author.

### 8. Pre-Push Quality Gates Work

preflight.sh blocks broken commits when enforced. Achieved 100% CI compliance.

### 9. Copilot-Proof Code Standard

Quality target: "No AI reviewer can suggest ANY improvements". Run GitHub Copilot review → ZERO suggestions = standard achieved.

### 10. Post-Merge Cleanup Protocol

Execute 5-command sequence after EVERY merge. Prevents orphaned branches, ensures sync.

### 11. Bot PR Validation

See `copilot-config.yaml:bot_pr_validation` for validation process. Validate against tech stack before accepting bot PRs.

---

**For complete details, validation commands, and structured data:** See `.github/copilot-config.yaml`

**Markdown length:** ~400 lines (target achieved) | **YAML contains:** All checklists, validations, multi-repo rules, complete tech stack
