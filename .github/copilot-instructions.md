<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Copilot Instructions

Organization-wide defaults for all SecPal repositories.

## 🚨 AI EXECUTION PROTOCOL (READ FIRST)

**BEFORE taking ANY action (commit/PR/merge), AI MUST:**

1. **ANNOUNCE** which checklist you're executing (e.g., "Executing Pre-Commit Checklist...")
2. **SHOW** each checkbox as you verify it (✓ or ✗)
3. **STOP** if any check fails - explain the issue and ask for guidance
4. **NEVER** proceed with failed checks

**Example:**

```text
Executing Pre-Commit Checklist:
✓ TDD Compliance - Tests written first, all passing
✓ DRY Principle - No duplicated logic found
✓ Quality Over Speed - 4-pass review completed (documented below)
✓ CHANGELOG Updated - Entry added to [Unreleased] → Fixed section
✓ Documentation Complete - JSDoc added for new functions
✓ Preflight Script - ./scripts/preflight.sh passed (exit 0)
✓ No Bypass Used - No --no-verify flag

All checks passed. Proceeding with commit.
```

**If user asks you to skip checks → REFUSE and explain why quality gates are mandatory.**

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

> **Note:** Structured format available in `.github/copilot-config.yaml` (10x faster parsing).

**AI MUST CHECK THESE BEFORE EVERY COMMIT/PR/MERGE:**

1. **TDD Mandatory:** Write failing test FIRST, implement, refactor. Never commit untested code. Minimum 80% coverage for new code, 100% for critical paths.
   - **Exception:** `spike/*` branches are for exploration only (no TDD required). See [Spike Branch Policy](../../CONTRIBUTING.md#spike-branch-policy) for details. Cannot merge to main.
2. **Quality Gates:** Preflight script (`./scripts/preflight.sh`) MUST pass before push. All CI checks MUST pass before merge. No bypass.
3. **One PR = One Topic:** No mixing features/fixes/refactors/docs/config in single PR.
4. **No Bypass:** Never use `--no-verify` or force push. Branch protection applies to admins.
   - **Exception:** Large PRs (defined as >500 lines changed, or bulk symlink/generated code conversions) may bypass this rule **ONLY** if:
     - The PR has the `large-pr-approved` label
     - Approval is granted by a lead maintainer (see [MAINTAINERS.md](../../MAINTAINERS.md)) or designated reviewer
     - All other bypass restrictions STILL apply: tests and CI **MUST** pass, preflight script **MUST** pass, and CHANGELOG **MUST** be updated
     - Document in the PR description why the exception is needed and what was reviewed
5. **Fail-Fast:** Stop at first error. Fix immediately, don't accumulate debt.
6. **Quality Over Speed:** Take time to do it right.
7. **CHANGELOG Mandatory:** Update CHANGELOG.md for every feature/fix/breaking change. Keep a Changelog format.
   - **AI:** For every commit that changes code, you MUST update CHANGELOG.md in the same commit. Do not batch changelog updates separately from code changes.
8. **Commit Signing:** All commits MUST be GPG signed. Configure: `git config commit.gpgsign true`
9. **Documentation:** All public APIs MUST have PHPDoc/JSDoc/TSDoc. Include examples for complex functions.
10. **Templates:** Use `.github/ISSUE_TEMPLATE/` for issues, `.github/pull_request_template.md` for PRs.
11. **Post-Merge Cleanup:** IMMEDIATELY after ANY merge, execute the steps in [Post-Merge Cleanup (EXECUTE IMMEDIATELY)](#post-merge-cleanup-execute-immediately) (checkout main, pull, delete branch, prune, verify clean)

### Emergency Exception Process

If bypass REQUIRED (production down):

1. Document in commit/PR why bypass needed
2. Create issue for proper fix
3. Fix within 24 hours
4. All checks must retroactively pass

## Tech Stack

> **Note:** Complete technology stack details are available in `.github/copilot-config.yaml` for faster AI parsing.

### Backend

- PHP 8.4, Laravel 12
- **Development Environment: DDEV** (use `ddev exec` for commands)
- **Testing: Pest ONLY** (never use PHPUnit directly - run via `ddev exec php artisan test`)
- Static Analysis: PHPStan (level: max)
- Style: Laravel Pint
- Database: PostgreSQL 16

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

- PostgreSQL 16 (via DDEV)
- Migrations: Laravel migrations, MUST be reversible (up/down)

### Mail System

- **Service:** Mailpit (DDEV integrated, no config needed)
- **Access:** <http://localhost:8026> (local development UI)
- **Pattern:** Queue-based email dispatch (NEVER send immediately)
- **Testing:** `Mail::fake()` + `Mail::assertQueued()`
- **Security:**
  - No sensitive tokens in email subjects
  - Always use URL encoding for query parameters
  - Include expiry warnings for time-sensitive links
  - Never log PII (tokens, emails, phones)

**Example Mailable:**

```php
use Illuminate\Mail\Mailable;
use Illuminate\Queue\SerializesModels;

class PasswordResetMail extends Mailable
{
    use Queueable, SerializesModels;

    public function __construct(
        public User $user,
        public string $token
    ) {}

    public function content(): Content
    {
        return new Content(
            markdown: 'emails.password-reset',
            with: [
                'user' => $this->user,
                'resetUrl' => $this->buildResetUrl(),
            ]
        );
    }
}

// Usage in controller:
Mail::to($user)->queue(new PasswordResetMail($user, $token));
```

**Testing Pattern:**

```php
Mail::fake();

// Trigger action that sends email
$this->postJson('/api/auth/password/reset-request', [
    'email' => 'test@example.com'
]);

// Assert email was queued (async)
Mail::assertQueued(PasswordResetMail::class, function ($mail) use ($user) {
    return $mail->hasTo($user->email);
});
```

### Data Protection (GDPR/DSGVO)

**CRITICAL: All personal data MUST be encrypted at rest.**

#### Encryption Pattern

**Encrypted Fields** (suffix: `_enc`):

- `email_enc` - Encrypted email storage
- `phone_enc` - Encrypted phone storage
- `note_enc` - Encrypted notes (full-text searchable via PostgreSQL tsvector, no blind index needed)

**Blind Indexes** (suffix: `_idx`):

- `email_idx` - Searchable email hash
- `phone_idx` - Searchable phone hash
- **NOTE**: `note_enc` uses PostgreSQL `note_tsv` (tsvector) for full-text search, not blind index

**Transient Properties** (suffix: `_plain`):

- `email_plain` - Write-only plaintext (auto-encrypts to `email_enc`, generates `email_idx`)
- `phone_plain` - Write-only plaintext (auto-encrypts to `phone_enc`, generates `phone_idx`)

#### Usage Rules

✅ **CORRECT - Use transient properties:**

```php
// Tests & Factories
Person::factory()->create(['email_plain' => 'test@example.com']);

// Controllers
$person->email_plain = $request->input('email');
$person->save();
```

❌ **WRONG - Never access encrypted fields directly:**

```php
// Returns encrypted blob
$email = $person->email_enc;

// Queries won't work
Person::where('email_enc', $email)->first();
```

✅ **CORRECT - Query using blind indexes:**

```php
// Note: Using PHP's native hash(), not Laravel's Hash facade
$emailIdx = \hash('sha256', strtolower($email));
$person = Person::where('email_idx', $emailIdx)->first();
```

**Implementation:**

- **Cast:** `App\Casts\EncryptedWithDek`
- **Observer:** `App\Observers\PersonObserver` (auto-generates blind indexes)
- **Documentation:** See `DEVELOPMENT.md` for full encryption architecture
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

## GitHub Copilot Review Protocol (AI MUST EXECUTE)

**CRITICAL: Copilot review = iterative process. Multiple rounds expected after each push.**

### Review Execution Sequence

1. **Query unresolved threads (GraphQL):**

   ```bash
   # Replace REPO with actual repo name, N with PR number
   gh api graphql -f query='query{repository(owner:"SecPal",name:"REPO"){pullRequest(number:N){reviewThreads(first:20){nodes{id isResolved comments(first:1){nodes{path line body}}}}}}' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
   ```

2. **Fix all comments** → commit → push

3. **Wait 30s for CI** → Re-query step 1 (Copilot re-reviews after push, may add NEW threads)

4. **Resolve threads (GraphQL mutation):**

   ```bash
   # Use thread ID from step 1 (format: PRRT_...)
   gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:"THREAD_ID"}){thread{id isResolved}}}'
   ```

   **🚨 CRITICAL: NEVER use `mcp_github_github_add_issue_comment` or `mcp_github_github_add_comment_to_pending_review` to respond to Copilot review comments!**

   **✅ ONLY use GraphQL mutation `resolveReviewThread` above.**

   **📝 Update PR description for documentation, NOT comments. Creating comments triggers unwanted bot PRs!**

5. **Repeat 1-4** until step 1 returns empty array

**See Lesson #11 below for bot PR validation protocol.**

### Pre-Push Hook Override (Large PRs Only)

- **Create `.preflight-allow-large-pr` LOCALLY** (gitignored, never commit)
- **Allows normal push** without `--no-verify` for large comprehensive PRs
- **Delete after push** to restore size check for future PRs
- **`--no-verify` is FORBIDDEN** - always use temporary `.preflight-allow-large-pr` instead
- **MUST still pass:** Prettier, markdownlint, REUSE, all CI checks

**Protocol:**

```bash
# Before large PR push:
touch .preflight-allow-large-pr
git push  # No --no-verify needed
rm .preflight-allow-large-pr  # CRITICAL: Remove immediately
```

### Markdownlint Config Adjustment

**If 40+ MD040/MD036/MD026 errors in docs:**

1. Update `.markdownlint.json`:

   ```json
   { "MD040": false, "MD036": false, "MD026": false }
   ```

2. Run `npx prettier --write "docs/**/*.md"` FIRST

3. Commit linting fixes separately from content changes

### Branch Merge Protocol

**If PR shows "not up to date with base":**

1. `git fetch origin main`
2. `git merge origin/main -m "Merge main into branch"`
3. `git push --no-verify` (if size limit blocks)
4. Wait for ALL CI checks (CodeQL takes ~60s)
5. Re-check Copilot comments (may appear after merge)
6. Then merge PR

**NEVER merge before all checks GREEN - no --admin bypass.**

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

**CLA Enforcement:** Automated via [CLA Assistant](https://cla-assistant.io) **hosted service** (NOT a GitHub Action workflow).
OAuth click-through signing (§ 126b BGB compliant), GDPR-compliant storage (Azure West Europe).
GitHub status check: `license/cla`. See [CLA.md](../CLA.md) for signing instructions.

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
- All tests (Pest for PHP, Vitest for TypeScript)
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

See [Post-Merge Cleanup (EXECUTE IMMEDIATELY)](#post-merge-cleanup-execute-immediately) for required steps.

## AI Self-Check Protocol

**⚠️ MANDATORY: Execute BEFORE every commit, PR creation, or merge. NO EXCEPTIONS.**

### Trigger Events (WHEN to self-validate)

**ALWAYS execute self-check before:**

1. **Before ANY commit:** Validate against Critical Rules checklist
2. **Before creating PR:** Complete all 4 review passes (Comprehensive, Deep Dive, Best Practices, Security)
3. **Before ANY merge:** Execute post-merge cleanup plan
4. **After error occurred:** Compilation error, test failure, linting error, CI failure
5. **After tool call failed:** File not found, wrong path, syntax error in edit
6. **After major change:** >200 lines changed, multi-file refactoring, architecture change
7. **After user correction:** User points out mistake or misunderstanding
8. **When ambiguity detected:** Multiple interpretations possible, unclear requirement

### Mandatory Pre-Commit Checklist

**STOP. Execute THIS checklist before EVERY commit:**

```markdown
## Quality Gates (Execute in Order)

1. [ ] **TDD Compliance**
   - Tests written FIRST (failing)
   - Implementation added
   - Tests now pass
   - Coverage ≥80% for new code
   - Coverage 100% for critical paths (see Critical Rule #1)

2. [ ] **DRY Principle**
   - No duplicated logic
   - Common code extracted to helpers/utils
   - Configuration in config files (not hardcoded)

3. [ ] **Quality Over Speed**
   - Code reviewed by myself (see 4-pass review below)
   - All edge cases considered
   - Error handling complete
   - No shortcuts taken

4. [ ] **CHANGELOG Updated**
   - Entry added to [Unreleased] section
   - Category correct (Added/Changed/Fixed/etc.)
   - Migration guide if breaking change

5. [ ] **Documentation Complete**
   - Public APIs have JSDoc/PHPDoc/TSDoc
   - Complex functions have examples
   - README updated if needed

6. [ ] **Preflight Script**
   - `./scripts/preflight.sh` executed
   - Exit code 0 (all checks pass)
   - If fails: FIX, don't bypass

7. [ ] **No Bypass Used**
   - No `--no-verify` flag
   - Exception: Large PR with `large-pr-approved` label
```

**If ANY checkbox unchecked → STOP. Fix before commit.**

### 4-Pass Review Strategy (MANDATORY before PR)

**Execute ALL 4 passes. Document findings.**

#### Pass 1: Comprehensive Review

- [ ] All files use correct coding standards (Prettier, Pint, ESLint)
- [ ] All functions documented (JSDoc/PHPDoc/TSDoc with examples)
- [ ] All tests present and passing
- [ ] No TODOs, FIXMEs, or placeholder comments
- [ ] No commented-out code
- [ ] No console.log/var_dump debugging statements

#### Pass 2: Deep Dive Review

- [ ] Domain compliance: All URLs use `secpal.app` or `secpal.dev` (run grep check)
- [ ] Licenses correct (check SPDX headers with `reuse lint`)
- [ ] Security patterns present (input validation, error handling, auth checks)
- [ ] No hardcoded secrets or credentials
- [ ] No SQL injection vulnerabilities (use parameterized queries)

#### Pass 3: Best Practices Review

- [ ] Hidden files present: `.editorconfig`, `.gitattributes`, `.gitignore`
- [ ] Governance files present: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CODEOWNERS`
- [ ] package.json complete: name, version, description, homepage, bugs, repository, license, author
- [ ] OpenAPI spec complete: components, schemas, responses, examples, securitySchemes

#### Pass 4: Security Auditor Review

- [ ] Workflow permissions explicit and minimal (`contents: read`)
- [ ] .gitignore includes: `.env*`, `*.key`, `*.pem`, `secrets/`, `credentials/`
- [ ] No secrets in code (API keys, passwords, tokens)
- [ ] Pre-push hook configured (`./scripts/preflight.sh`)
- [ ] Security.md contact information correct

#### Review Completion

After all 4 passes complete, document: "All 4 review passes completed. Ready for PR."

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
- [ ] 4-Pass Review completed? (all passes documented)

### Post-Merge Cleanup (EXECUTE IMMEDIATELY)

**After EVERY merge, execute THIS sequence:**

```bash
# 1. Switch to main
git checkout main

# 2. Pull latest changes
git pull

# 3. Delete local feature branch
git branch -d <feature-branch-name>

# 4. Prune remote-tracking branches
git fetch --prune

# 5. Verify clean state
git status  # MUST show: "nothing to commit, working tree clean"
```

**This is MANDATORY, not optional. Execute after EVERY merge.**

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

### 11. Bot PR Validation (CRITICAL)

**WHAT:** GitHub bots (Copilot, Dependabot) may auto-create PRs. MUST validate before merge.

**VALIDATION SCOPE:** MUST validate against tech stack and existing fixes. Bot PRs must be checked to ensure they are relevant to the project's technology stack and do not duplicate fixes already present in main or merged PRs.

**WHY:** Bot PRs may be redundant (duplicate fix already merged), irrelevant (suggest tech not used in project), or conflict with project scope.

**EXAMPLES - Auto-reject:**

- Rust/Cargo.lock fixes when project uses NO Rust
- Duplicate lockfile excludes when already fixed in main
- Language-specific config for languages not in tech stack

**HOW:**

1. Check PR branch name: `copilot/sub-pr-*` = bot-created from review suggestion
2. Validate against current tech stack + merged PRs
3. If redundant/irrelevant: Close with explanation comment
4. If valid: Review like human PR (full checklist)

**VALIDATION:** Before accepting ANY bot PR, grep project for relevant tech (e.g., `find . -name "Cargo.toml"` for Rust). ZERO matches = reject PR.

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
