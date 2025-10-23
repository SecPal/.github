<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Copilot Instructions

Organization-wide defaults for all SecPal repositories.

## Repository Structure

```text
SecPal Organization:
├── .github/     - Organization defaults (this repo)
├── api/         - Laravel backend (planned)
├── frontend/    - React frontend (planned)
└── contracts/   - OpenAPI contracts (planned)

Local: <workspace>/SecPal/<repository>
Remote: https://github.com/SecPal/<repository>
```

## Critical Rules

1. **TDD Mandatory:** Write failing test FIRST, implement, refactor. Never commit untested code. Minimum 80% coverage for new code, 100% for critical paths.
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

**Default:** AGPL-3.0-or-later

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
7. Copilot review completed (mandatory for code changes)
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

---
