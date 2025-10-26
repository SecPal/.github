<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Copilot Instructions

Organization-wide defaults for all SecPal repositories.

## Repository Structure

```text
SecPal Organization:
├── .github/     - Organization-wide settings and documentation
├── api/         - Laravel backend (planned)
├── frontend/    - React/TypeScript frontend
└── contracts/   - OpenAPI 3.1 specifications

Local: <workspace>/SecPal/<repository>
Remote: https://github.com/SecPal/<repository>
```

## Critical Rules

1. **TDD Mandatory:** Write failing test FIRST, implement, refactor. Never commit untested code. Minimum 80% coverage for new code, 100% for critical paths.
   - **Exception:** `spike/*` branches are for exploration only (no TDD required). See [Spike Branch Policy](../../CONTRIBUTING.md#spike-branch-policy) for details. Cannot merge to main.
2. **Quality Gates:** Preflight script (`./scripts/preflight.sh`) MUST pass before push. All CI checks MUST pass before merge. No bypass.
3. **One PR = One Topic:** No mixing features/fixes/refactors/docs/config in single PR.
4. **No Bypass:** Never use `--no-verify` or force push. Branch protection applies to admins.
5. **Fail-Fast:** Stop at first error. Fix immediately, don't accumulate debt.
6. **Quality Over Speed:** Take time to do it right.
7. **CHANGELOG Mandatory:** Update CHANGELOG.md for every feature/fix/breaking change. Keep a Changelog format.
8. **Commit Signing:** All commits MUST be GPG signed. Configure: `git config commit.gpgsign true`
9. **Documentation:** All public APIs MUST have PHPDoc/JSDoc/TSDoc. Include examples for complex functions.
10. **Templates:** Use `.github/ISSUE_TEMPLATE/` for issues, `.github/pull_request_template.md` for PRs.

### Emergency Exception Process

If bypass REQUIRED (production down):

1. Document in commit/PR why bypass needed
2. Create issue for proper fix
3. Fix within 24 hours
4. All checks must retroactively pass

## Tech Stack

### Backend

- PHP 8.4, Laravel 12
- Testing: Pest/PHPUnit
- Static Analysis: PHPStan (level: max)
- Style: Laravel Pint
- Database: PostgreSQL (planned)

### Frontend

- Node 22.x, React, TypeScript (strict)
- Build: Vite
- Linting: ESLint
- Testing: Vitest + React Testing Library

### API

- OpenAPI 3.1 (single source of truth)
- Location: `docs/openapi.yaml`
- Style: REST, JSON responses
- Versioning: URL-based (`/api/v1/`, `/api/v2/`)
- Authentication: Bearer tokens (JWT planned)

### Database

- PostgreSQL (production)
- SQLite (testing)
- Migrations: Laravel migrations, MUST be reversible (up/down)
- Seeds: Separate for dev/test/prod

### Version Control

- Git with signed commits (GPG mandatory)
- Linear history only
- Conventional Commits

## Multi-Repo Coordination

When changes span multiple repositories:

1. **Update `contracts/` FIRST** (OpenAPI schema changes)
2. **Then `api/` and `frontend/` in parallel** (implement contract)
3. **Version lock:** Tag contracts before implementing
4. **Breaking changes:** New API version (`/api/v2/`), deprecate old version

## Versioning (Software Repositories Only)

**Note:** Only `api/`, `frontend/`, `contracts/` repositories use SEMVER. This `.github` repository is NOT versioned.

**SEMVER 2.0.0** starting at **0.0.1**

```text
0.x.x (development): Breaking changes allowed in MINOR bumps, no compatibility guarantees
1.x.x+ (stable): MAJOR=breaking, MINOR=features, PATCH=fixes

Tags: vMAJOR.MINOR.PATCH (signed)
API URLs: /api/v1/, /api/v2/, etc.
Deprecation: 6 months minimum for stable APIs
```

### Breaking Changes Process

**Development (0.x.x):**

- Document in CHANGELOG.md with migration guide
- Breaking changes in MINOR version OK

**Stable (1.x.x+):**

- MAJOR version bump required
- Deprecation warnings 1 version before removal
- Keep old version for 6 months minimum
- Migration guide in CHANGELOG.md
- API: New version path (`/api/v2/`), parallel support

### CHANGELOG Maintenance

**For `.github` repository:**

- Chronological log format (date-based sections)
- Document major governance/template changes
- No version sections, no [Unreleased] section

**For software repositories (`api/`, `frontend/`, `contracts/`):**

**Format:** Keep a Changelog 1.1.0

**Required entries:**

- `[Unreleased]` section for ongoing work
- Version sections: `[X.Y.Z] - YYYY-MM-DD`
- Categories: Added, Changed, Deprecated, Removed, Fixed, Security

**Update timing:**

- Feature PR: Add to `[Unreleased]` → Added
- Bug fix PR: Add to `[Unreleased]` → Fixed
- Breaking change: Add to `[Unreleased]` → Changed/Removed with migration guide
- Release: Move `[Unreleased]` to `[X.Y.Z] - date`, create new `[Unreleased]`

## Licensing

**Dual-Licensing Model:**

SecPal uses a **dual-licensing strategy**:

1. **Open Source (AGPL-3.0-or-later)**: Default for all code, ensuring copyleft compliance
2. **Commercial License**: Available for customers requiring proprietary use

**Default License:** AGPL-3.0-or-later

**By File Type:**

- Application code (`*.php`, `*.ts`, `*.js`): `AGPL-3.0-or-later`
- Configuration (`*.yaml`, `*.json`, `*.toml`): `CC0-1.0`
- Helper scripts (`*.sh`): `MIT`
- Documentation (`*.md`): `CC0-1.0`

**Compatible Dependencies:**

- Permissive: MIT, `BSD-*`, Apache-2.0, ISC
- Weak Copyleft: `LGPL-*`, MPL-2.0
- Strong Copyleft: GPL-3.0-or-later, AGPL-3.0-or-later
- Public Domain: CC0-1.0, Unlicense

**Incompatible:**

- GPL-2.0-only (without "or later")
- Proprietary/Commercial licenses
- Creative Commons (except CC0)

Whitelist: `.github/license-whitelist.txt`

**Contributor License Agreement (CLA):**

All contributors must sign the [CLA](../CLA.md) to:

- Grant rights for both AGPL and commercial distribution
- Retain copyright ownership of contributions
- Enable dual-licensing business model

**CLA Enforcement:** Automated via [CLA Assistant](https://cla-assistant.io) **hosted service** (NOT a GitHub Action workflow). OAuth click-through signing (§ 126b BGB compliant), GDPR-compliant storage (Azure West Europe). GitHub status check: `license/cla`. See [CLA.md](../CLA.md) for signing instructions.

## Repository Visibility

**All repositories PUBLIC by default.**

- AGPL compliance (source code availability)
- Secret scanning + push protection enabled
- Security vulnerabilities: Use GitHub Security Advisories (private disclosure)
- Response timeline: See SECURITY.md (Critical: 24h response, 7d fix)
- NO public issues for security vulnerabilities

## Dependencies

**Dependabot:** Daily checks 04:00 CET, all ecosystems (npm, composer, pip, docker, github-actions)

- Creates PRs for all updates (patch, minor, major)
- Security updates prioritized
- Manual review for major versions

## Quality Standards

**REUSE 3.3:** All files MUST have SPDX headers

- Use `REUSE.toml` for bulk licensing (not deprecated `.reuse/dep5`)
- Run `reuse lint` before commit (enforced via pre-commit hook)

**Code Style:**

- Markdown/YAML/JSON/TS/JS: Prettier
- PHP: Laravel Pint
- Linting: ESLint (JS/TS), PHPStan level:max (PHP)
- Markdown: markdownlint
- Shell: shellcheck
- GitHub Actions: actionlint

## Quality Gates (3-Stage)

### 1. Pre-Commit (Fast)

- REUSE compliance
- Prettier (auto-fix)
- Markdownlint
- yamllint
- actionlint
- shellcheck

### 2. Pre-Push (Comprehensive)

- All pre-commit checks
- PHPStan / ESLint
- All tests (Pest/Vitest)
- OpenAPI validation
- Script: `scripts/preflight.sh`

### 3. CI (Enforcement)

- All pre-push checks
- CodeQL (JS/TS only, NOT PHP)
- Branch protection blocks merge if failed

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

**Size:** ≤600 lines changed (excluding generated code, lock files)

- > 600 lines: Split into multiple PRs
- Exception: Initial setup, large refactors (document why)

**One Topic Rule (HARD CONSTRAINT):**

Prohibited combinations in single PR:

- Feature + Bug Fix
- Feature + Refactor
- Feature + Documentation
- Feature + Dependency Update
- Bug Fix + Refactor
- Multiple unrelated features
- Code + Config/Infrastructure

Allowed combinations:

- Feature + Tests for that feature
- Bug fix + Tests for that fix
- Feature + Documentation for that feature only
- Refactor + Updated tests for refactored code

**Branch Naming:**

- `feat/description` - New features
- `fix/description` - Bug fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation only
- `test/description` - Test improvements
- `chore/description` - Maintenance (deps, configs)

**Commit Convention:**

```text
type(scope): description

feat: add feature
fix: resolve bug
refactor: restructure code
docs: update documentation
test: add tests
chore: update dependencies
```

**PR Checklist:**

1. All checks GREEN locally and CI
2. ≤600 lines
3. ONE topic only
4. Self-reviewed
5. Description complete
6. Tests pass
7. No `--no-verify` used

## Workflows

### Before Commit

```bash
# Run pre-commit checks manually if needed
pre-commit run --all-files

# Or specific hook
pre-commit run reuse --all-files
```

### Before Push

```bash
# Run comprehensive checks
./scripts/preflight.sh

# Or manually per repo type
npm test && npm run lint && npm run typecheck  # Frontend
./vendor/bin/pint && ./vendor/bin/phpstan analyse && php artisan test  # Backend
npx @stoplight/spectral-cli lint docs/openapi.yaml  # API
reuse lint  # REUSE
```

### During PR Review

1. All automated checks GREEN?
2. PR ≤600 lines?
3. One topic only?
4. CHANGELOG.md updated?
5. Documentation updated (if public API changed)?
6. Tests added/updated?
7. Copilot review requested (recommended for code changes)
8. Address all feedback
9. All threads resolved?

### Before Merge

- All required checks GREEN
- Copilot review completed and approved
- All conversations resolved
- CHANGELOG.md entry exists
- Squash commits

## AI Self-Check Protocol

### Trigger Events (WHEN to self-validate)

Execute self-check immediately when:

1. **Error occurred:** Compilation error, test failure, linting error, CI failure
2. **Tool call failed:** File not found, wrong path, syntax error in edit
3. **Constraint violated:** Realized a Critical Rule was broken
4. **Instructions incomplete:** Missing information needed to complete task
5. **After major change:** >200 lines changed, multi-file refactoring, architecture change
6. **User correction:** User points out mistake or misunderstanding
7. **Ambiguity detected:** Multiple interpretations possible, unclear requirement

### Validation Checklist (WHAT to verify)

Before completing any task, verify:

- [ ] All Critical Rules followed? (TDD, One Topic, No Bypass, CHANGELOG, etc.)
- [ ] Preflight script would pass? (formatting, linting, tests, REUSE)
- [ ] CHANGELOG.md updated? (if feature/fix/breaking change)
- [ ] Tests added/updated? (80% coverage minimum)
- [ ] Documentation updated? (if public API changed)
- [ ] Correct repository context? (api/ vs frontend/ vs contracts/)
- [ ] Multi-repo coordination needed? (contracts first?)
- [ ] Breaking change? (MAJOR version bump, deprecation process)
- [ ] Security implications? (use SECURITY.md process if needed)
- [ ] Commit convention followed? (type(scope): description)

### Instructions Update Process (HOW to improve)

When Instructions were insufficient:

1. **Document gap:** What information was missing? What assumption was wrong?
2. **Propose addition:** Draft new constraint/guideline in terse, factual format
3. **Create issue:** `.github/ISSUE_TEMPLATE/documentation.yml` - "Copilot Instructions: [gap]"
4. **Include context:** What task triggered the gap? What went wrong?
5. **PR with update:** Branch `docs/copilot-instructions-[topic]`, update this file
6. **Keep compact:** Add essentials only, maintain <400 lines target

## Learned Lessons (Copilot-Proof Standard)

### 1. Multi-Layer Review Strategy (MANDATORY)

**WHAT:** Execute 4 review passes with different perspectives before creating PR.

**WHY:** Single-pass reviews miss 60%+ of issues (domain errors, security gaps, missing best practices).

**HOW:**

1. **Comprehensive Review:** Verify all files meet coding standards, documentation complete, tests present
2. **Deep Dive Review:** Check critical policies (domain names, license compliance, security patterns)
3. **Best Practices Review:** Search for missing governance files (.editorconfig, .gitattributes, CODEOWNERS, SECURITY.md)
4. **Security Auditor Review:** Verify workflow permissions, .gitignore coverage, secret patterns

**VALIDATION:** Run all 4 passes before PR creation. Document findings. Fix all issues before commit.

### 2. Domain Policy (CRITICAL - ZERO TOLERANCE)

**WHAT:** SecPal ONLY uses these domains:

- **Production/All Services:** secpal.app (including email addresses)
- **Development:** secpal.dev (infrastructure endpoints only, NEVER for email addresses)
  - **All email addresses (including development):** MUST use secpal.app
- **FORBIDDEN:** secpal.com, secpal.org, ANY other domain

**WHY:** Incorrect domains expose critical infrastructure errors. Found 6 instances of secpal.org in previous commits.

**HOW:**

1. MUST run `grep -r "secpal\." --include="*.md" --include="*.yaml" --include="*.json" --include="*.sh"` before EVERY commit
2. MUST validate all email addresses use @secpal.app
3. MUST check package.json, README.md, SECURITY.md, OpenAPI specs
4. ZERO exceptions - this is a hard blocker

**VALIDATION:** `grep` returns ONLY secpal.app and secpal.dev. Any other match = PR rejected.

### 3. Governance File Distribution

**WHAT:** Governance files are copied from .github repo to maintain consistency.

**WHY:** While symlinks would be ideal for DRY, they don't render properly on GitHub.com web interface (only show as text paths). Real file copies ensure proper display for all users.

**HOW:**

**Copied files (from .github to frontend/contracts):**

```bash
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
CODEOWNERS
.editorconfig
.gitattributes
```

**Update Process:**

After merging changes to governance files in the `.github` repository, copy them to all other repositories to maintain consistency:

```bash
# From SecPal workspace root
cp .github/CONTRIBUTING.md frontend/
cp .github/CONTRIBUTING.md contracts/
cp .github/SECURITY.md frontend/
cp .github/SECURITY.md contracts/
# ... repeat for other files as needed
```

**Automation Note:** For future improvement, consider creating a sync script (e.g., `.github/scripts/sync-governance.sh`) to automate this process and reduce manual errors.

**Note:** Yes, this violates pure DRY, but it's a pragmatic trade-off for usability on GitHub.com.

**VALIDATION:** Verify governance files exist and match across repositories:

```bash
# Quick check for file existence
for repo in frontend contracts; do
  for file in CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md CODEOWNERS .editorconfig .gitattributes; do
    [ -f "$repo/$file" ] && echo "✅ $repo/$file" || echo "❌ $repo/$file missing"
  done
done
```

### 4. Security by Default, not by Addition (MANDATORY)

**WHAT:** Security MUST be explicit from line 1, not added later.

**WHY:** Default permissive settings = privilege escalation risk. Principle of Least Privilege.

**HOW:**

**GitHub Actions Workflows:**

```yaml
# ✅ REQUIRED - Explicit permissions
permissions:
  contents: read # Minimal required access

# ❌ FORBIDDEN - Implicit permissions
# (no permissions block = write-all access)
```

**File Types:**

```yaml
# .gitignore MUST include (minimum):
.env*
*.key
*.pem
secrets/
credentials/
*.secret
.aws/
.azure/
.gcloud/
```

**Pre-Push Hooks:** MUST validate security before allowing push (preflight.sh).

**VALIDATION:** Run `grep -L "^permissions:" .github/workflows/*.yml` - MUST produce no output (all files contain permissions block). All workflows require explicit permissions.

### 5. Hidden Files Have Equal Priority (MANDATORY)

**WHAT:** Hidden files (.editorconfig, .gitattributes, .gitignore, CODEOWNERS) are EQUALLY critical as source code.

**WHY:** Missing hidden files = inconsistent line endings, wrong git behavior, team friction, security gaps.

**HOW:**

**Required hidden files (per repository):**

- `.editorconfig` - Code style enforcement (indent, charset, trim trailing whitespace)
- `.gitattributes` - Line ending normalization (LF for text, binary handling)
- `.gitignore` - Secret prevention, build artifact exclusion
- `CODEOWNERS` - Automatic review assignment

**Review protocol:** MUST explicitly validate presence. DO NOT skip because filename starts with dot.

**VALIDATION:** Execute `ls -la | grep "^\."` - MUST show all 4 files. Missing file = incomplete setup = PR blocked.

### 6. OpenAPI is More Than Endpoints (MANDATORY)

**WHAT:** OpenAPI specs MUST include complete infrastructure from v0.0.1:

- Components (schemas, responses, parameters, examples, securitySchemes)
- Security definitions (authentication, rate limiting)
- Server configuration (base URLs, environments)
- Complete error schemas (4xx, 5xx)
- Rate limiting documentation
- CORS policy
- Header specifications

**WHY:** Incomplete specs = implementation assumptions = API drift = breaking changes.

**HOW:**

```yaml
# ✅ REQUIRED from v0.0.1
openapi: 3.1.0
info: # Full metadata
servers: # All environments
security: # Global security
components:
  schemas: # All data models
  responses: # Standard errors
  parameters: # Reusable params
  examples: # Request/response examples
  securitySchemes: # Auth methods
paths: # API endpoints
```

**VALIDATION:** Every OpenAPI file MUST have all 7 top-level sections before merge.

### 7. package.json Must Include Complete Metadata (MANDATORY)

**WHAT:** package.json MUST include complete metadata from v0.0.1:

```json
{
  "name": "@secpal/contracts",
  "version": "0.0.1",
  "description": "Complete professional description",
  "keywords": ["api", "openapi", "contracts"],
  "homepage": "https://secpal.app",
  "bugs": "https://github.com/SecPal/contracts/issues",
  "repository": {
    "type": "git",
    "url": "https://github.com/SecPal/contracts"
  },
  "license": "AGPL-3.0-or-later",
  "author": "SecPal <info@secpal.app>"
}
```

**WHY:** Professional metadata = discoverability = trust = easier adoption.

**HOW:** Copy template from `.github/templates/package.json.template` and customize per repository.

**VALIDATION:** For each required field, execute individual command and verify non-empty value:

```bash
npm pkg get homepage   # MUST return non-empty
npm pkg get bugs       # MUST return non-empty
npm pkg get repository # MUST return non-empty
npm pkg get license    # MUST return non-empty
npm pkg get author     # MUST return non-empty
```

ZERO empty fields allowed.

### 8. Pre-Push Quality Gates Are Effective (MANDATORY)

**WHAT:** preflight.sh MUST execute before EVERY push and MUST block on failure.

**WHY:** Achieved 100% CI compliance when enforced. Prevents broken commits from reaching remote.

**HOW:**

```bash
# .git/hooks/pre-push
#!/bin/bash
./scripts/preflight.sh || exit 1
```

**Preflight checks (all MUST pass):**

1. REUSE compliance (SPDX headers)
2. Prettier formatting
3. Linting (ESLint/PHPStan/actionlint/markdownlint)
4. Tests (100% pass rate)
5. OpenAPI validation (contracts repository)

**VALIDATION:** Push with intentional error - MUST be blocked. Fix error - push succeeds.

### 9. Copilot-Proof Code Standard (MANDATORY)

**WHAT:** Code quality target = "No AI reviewer can suggest ANY improvements".

**WHY:** This is the professional standard. Anything less is technical debt from day 1.

**HOW - Validation Checklist:**

- [ ] All automated checks GREEN (REUSE, Prettier, linting, tests)
- [ ] Zero placeholder comments (TODO, FIXME, XXX) in final PR – all TODOs must be resolved before creating PR
- [ ] Zero commented-out code blocks
- [ ] No console.log / var_dump debugging statements
- [ ] No hardcoded values that should be config
- [ ] All functions documented (PHPDoc/JSDoc/TSDoc)
- [ ] All edge cases tested
- [ ] All error paths covered
- [ ] No magic numbers without explanation
- [ ] No violations of SOLID/DRY principles

**EXPECTATION:** Run GitHub Copilot review → "No issues found" with ZERO suggestions.

**VALIDATION:** Request Copilot review before merge. ANY suggestion = not ready.

### 10. Systematic Post-Merge Cleanup (MANDATORY)

**WHAT:** Immediately after PR merge, execute cleanup protocol:

```bash
# Execute in sequence after EVERY merge
git checkout main
git pull
git branch -d feature/branch-name
git fetch --prune
git status  # MUST output: "nothing to commit, working tree clean"
```

**WHY:** Prevents orphaned branches, ensures local/remote sync, avoids confusion.

**HOW:** Execute ALL 5 commands sequentially after EVERY merge. No exceptions.

**VALIDATION:** Execute `git branch -a` - MUST show ONLY main locally, ZERO feature/fix branches.

## Mandatory Checklists (Pre-PR Gates)

### Checklist 1: Multi-Pass Review Strategy

MUST complete ALL passes before creating PR:

- [ ] **Pass 1 - Comprehensive Review:** All files meet standards, docs complete, tests present
- [ ] **Pass 2 - Deep Dive Review:** Domain policy verified (grep secpal.), licenses correct, security patterns present
- [ ] **Pass 3 - Best Practices Review:** Hidden files present (.editorconfig, .gitattributes, CODEOWNERS, SECURITY.md)
- [ ] **Pass 4 - Security Auditor Review:** Workflow permissions explicit, .gitignore complete, zero secrets in code

### Checklist 2: Security Validation

Verify ALL items before commit. ZERO exceptions.

- [ ] Workflow permissions explicitly set to minimum required (`contents: read`)
- [ ] .gitignore includes: `.env*`, `*.key`, `*.pem`, `secrets/`, `credentials/`, `*.secret`
- [ ] Zero secrets in code (API keys, passwords, tokens)
- [ ] Pre-push hook configured (preflight.sh blocks on failure)

### Checklist 3: Completeness Validation

Verify ALL items before PR creation.

- [ ] OpenAPI specs include: components, schemas, responses, parameters, examples, securitySchemes, servers
- [ ] package.json includes: name, version, description, keywords, homepage, bugs, repository, license, author
- [ ] Governance files present (copied from .github): CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, CODEOWNERS
- [ ] Hidden files present: .editorconfig, .gitattributes, .gitignore

### Checklist 4: Quality Gates

ALL gates MUST pass before push. No bypass allowed.

- [ ] `./scripts/preflight.sh` exits with code 0
- [ ] `grep -r "secpal\." --include="*.md" --include="*.yaml" --include="*.json" --include="*.sh"` returns ONLY secpal.app and secpal.dev
- [ ] All tests pass (100% success rate)
- [ ] REUSE compliance: `reuse lint` returns 0 errors

### Checklist 5: Copilot-Proof Standard

Achieve ALL criteria before requesting review.

- [ ] Zero TODO/FIXME/XXX comments
- [ ] Zero commented-out code
- [ ] Zero debugging statements (console.log, var_dump)
- [ ] All functions documented (PHPDoc/JSDoc/TSDoc with examples)
- [ ] Zero magic numbers (all constants named and explained)
- [ ] GitHub Copilot review requested → ZERO improvement suggestions
- [ ] All conversations resolved
- [ ] CHANGELOG.md updated
- [ ] All CI checks GREEN

**TARGET:** All checks GREEN. Zero Copilot suggestions = standard achieved.

---
