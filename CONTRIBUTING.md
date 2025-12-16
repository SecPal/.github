<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Contributing to SecPal

We welcome contributions to SecPal! Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Development Setup

### Prerequisites

Ensure you have the following tools installed:

- **Git** with GPG signing configured
- **Node.js** (v22.x) and npm/pnpm/yarn
- **PHP** 8.4 and Composer (for backend projects)
- **Pre-commit** hooks tool (optional but recommended)

### Local Setup

**Recommended Workspace Structure:**

Create a dedicated directory for all SecPal repositories. This mirrors the GitHub organization structure:

```bash
<your-workspace>/SecPal/
├── .github/          # Organization-wide settings and documentation
├── api/              # Laravel backend (planned)
├── frontend/         # React/TypeScript frontend
└── contracts/        # OpenAPI 3.1 specifications
```

**Examples:**

- Linux/macOS: `~/projects/SecPal/` or `~/code/SecPal/`
- Windows: `C:\Dev\SecPal\` or `%USERPROFILE%\projects\SecPal\`

**Choose your workspace location and follow these steps:**

1. **Clone the repository:**

   ```bash
   # Create workspace directory (choose your preferred location)
   mkdir -p ~/projects/SecPal  # or C:\Dev\SecPal on Windows
   cd ~/projects/SecPal

   # Clone repository
   git clone https://github.com/SecPal/<repository>.git
   cd <repository>
   ```

2. **Set up Git hooks:**

   Install both pre-commit and pre-push hooks:

   ```bash
   # Install pre-commit (requires pre-commit to be installed first)
   pip install --user pre-commit
   ./scripts/setup-pre-commit.sh

   # Install pre-push hook
   ./scripts/setup-pre-push.sh
   ```

### Local Development Workflow

Before pushing your changes, run the preflight script to ensure everything passes:

```bash
./scripts/preflight.sh
```

This script runs automatically before every `git push` via the pre-push hook.

**What the preflight script checks:**

- Code formatting (Prettier)
- Markdown linting
- Workflow linting (actionlint)
- REUSE compliance
- PHP linting and tests (if applicable)
- Node.js linting and tests (if applicable)
- OpenAPI validation (if applicable)
- PR size (< 600 lines recommended, excluding lock files and license files)

**Excluded from PR size calculation:**

The following files are automatically excluded from the 600-line limit because they are auto-generated or boilerplate:

- `package-lock.json`, `composer.lock`, `yarn.lock`, `pnpm-lock.yaml` (dependency lock files)
- `LICENSES/*.txt` (license boilerplate files)

These exclusions are configured in `.preflight-exclude` and match the GitHub CI workflow. You can add project-specific patterns by editing this file.

**Bypassing the PR size check locally:**

If you need to work on a large PR that is justified (see exceptions below), you can temporarily bypass the 600-line limit:

```bash
# Create override file to allow large PR
touch .preflight-allow-large-pr

# Work on your changes
git add .
git commit -m "Your changes"
git push

# Clean up after merge
rm .preflight-allow-large-pr
```

⚠️ **Important:** The override file is automatically ignored by git and should only be used for exceptional cases that match the criteria below.

## How to Contribute

1. **Fork the repository** and create a new branch from `main`.
2. **Create a feature branch** using our naming convention (see below).
3. **Write your code** and add tests where applicable.
4. **Ensure all tests pass** locally by running `./scripts/preflight.sh`.
5. **Sign your commits** with GPG (see below).
6. **Push your branch** and open a pull request against `main`.

All pull requests will be reviewed by a maintainer and by GitHub Copilot.

## Pull Request Rules

### One PR = One Topic (NO MIXING)

**CRITICAL: Every PR must address exactly ONE logical topic.**

✅ **Allowed:**

- One feature (implementation + tests + docs for that feature)
- One bug fix (fix + regression test for that bug)
- One refactor (refactor + updated tests for that code)
- One documentation update (docs for one topic)

❌ **Strictly Prohibited:**

- Feature + Refactor
- Fix + Documentation (unrelated)
- Lint + Logic changes
- Multiple unrelated features
- Any "while I'm here" additions

**Example violations:**

- ❌ "Add user auth + refactor database + fix README typos" → Split into 3 PRs
- ❌ "Fix payment bug + add logging to user service" → Split into 2 PRs

**Why this rule exists:**

- Better review quality (focused review)
- Safer reverts (one topic = one revert)
- Clearer git history
- Faster merging

**If tempted to add "just one more thing":** Stop, create a separate branch and PR.

### PR Size Limit

Keep PRs **≤ 600 changed lines** for maintainability. If larger, split into sequential PRs:

1. Infrastructure/types/interfaces
2. Core implementation
3. Tests and documentation

**Exceptions:**

Large PRs (> 600 lines) are acceptable for:

- **Dependency updates** (e.g., `package-lock.json`, `Cargo.lock`)
- **Generated code** (e.g., OpenAPI clients, database migrations)
- **Boilerplate/templates** that cannot be reasonably split

**On GitHub:** Add the `large-pr-approved` label to bypass the size check. See [Organization Label Standards](https://github.com/SecPal/.github/blob/main/docs/labels.md) for details.

**Locally:** Create a `.preflight-allow-large-pr` file in the repository root to bypass the preflight check (see "Bypassing the PR size check locally" above).

## Branch Naming Convention

Use the following prefixes for your branch names:

- `feat/` - New features (e.g., `feat/add-user-profile`)
- `fix/` - Bug fixes (e.g., `fix/login-redirect`)
- `chore/` - Maintenance tasks (e.g., `chore/update-dependencies`)
- `docs/` - Documentation changes (e.g., `docs/update-readme`)
- `refactor/` - Code refactoring (e.g., `refactor/simplify-auth`)
- `test/` - Test additions or fixes (e.g., `test/add-e2e-tests`)
- `spike/` - Exploration/prototyping (see [Spike Branch Policy](#spike-branch-policy))

### Spike Branch Policy

**Spike branches** are for exploration, prototyping, and learning - **NOT for production code**.

**Purpose:**

- Evaluate new libraries or technologies
- Prototype UI/UX concepts
- Performance testing and benchmarking
- Learning unfamiliar APIs

**Rules:**

1. ✅ **TDD is optional** - Tests are not required in spike branches
2. ❌ **Cannot merge to `main`** - Spike branches are isolated
3. ⏰ **Time-limited** - Recommended lifecycle: 7 days max
4. 🔄 **Extract knowledge** - Create `feature/*` branch with tests for production
5. 🧹 **Clean up** - Delete spike branch after knowledge extraction

**Workflow:**

```bash
# 1. Create spike branch for exploration
git checkout -b spike/auth-library-evaluation

# 2. Experiment freely (no TDD required)
# ... code, test, evaluate ...

# 3. Document findings (in PR description or issue comment)

# 4. If you opened a PR for the spike branch:
#    - Add a summary of findings to the PR description or linked issue
#    - Close the PR before deleting the branch

# 5. Create feature branch WITH tests for production
git checkout main
git checkout -b feature/implement-auth-library
# ... implement with TDD ...

# 6. Delete spike branch (after closing any open PRs)
git branch -D spike/auth-library-evaluation
git push origin --delete spike/auth-library-evaluation
```

> **Note:** If you opened a PR for your spike branch, always close it and document your findings in the PR description or a related issue before deleting the branch. This keeps the repository clean and ensures knowledge is preserved.

**Examples:**

- `spike/nextauth-vs-passport-comparison`
- `spike/tailwind-component-layout`
- `spike/redis-caching-performance`
- `spike/websocket-real-time-updates`

**What spike branches are NOT:**

- ❌ A way to avoid writing tests for production code
- ❌ Long-lived feature development branches
- ❌ Code that will be directly merged to main

**CI Behavior:**

- ✅ Formatting checks **STILL RUN** (Prettier, linting)
- ✅ REUSE compliance **STILL REQUIRED**
- ⏭️ **Test suites are SKIPPED** (no TDD enforcement)

---

## Code Coverage

SecPal uses [Codecov](https://codecov.io) for automated code coverage tracking across all repositories.

### Coverage Requirements

- **Minimum Coverage:** 80% for new code (enforced by Codecov)
- **Critical Paths:** 100% coverage required (authentication, encryption, RBAC)
- **Coverage Reports:** Auto-generated in CI and uploaded to Codecov
- **PR Impact:** PRs must not decrease overall coverage below 80%

### Viewing Coverage

- **Codecov Dashboard:** [https://codecov.io/gh/SecPal](https://codecov.io/gh/SecPal)
- **PR Comments:** Codecov automatically comments on PRs with coverage impact
- **Badges:** Coverage badges displayed in each repository README

### Local Coverage Reports

**Backend (PHP/Laravel):**

```bash
# Run tests with coverage
ddev exec php artisan test --coverage-clover coverage.xml

# View HTML report
ddev exec php artisan test --coverage-html coverage-html/
open coverage-html/index.html
```

**Frontend (TypeScript/React):**

```bash
# Run tests with coverage
npm run test:coverage

# View HTML report (auto-opens in browser)
open coverage/index.html
```

### Coverage Configuration

- **Organization Config:** `.codecov.yml` in `.github` repository
- **Backend Config:** PHPUnit coverage in `phpunit.xml` (`<source>` element)
- **Frontend Config:** Vitest coverage in `vite.config.ts` (`test.coverage`)

### Exclusions

The following are excluded from coverage:

- Test files (`**/*Test.php`, `**/*.test.ts`, etc.)
- Configuration files (`**/*.config.ts`, `**/*.config.js`)
- Type definitions (`**/*.d.ts`)
- Database migrations and seeders
- Build artifacts and dependencies

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/) for clear and structured commit messages:

```text
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat:` - New feature
- `fix:` - Bug fix
- `chore:` - Maintenance/tooling
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, no logic change)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `perf:` - Performance improvements
- `ci:` - CI/CD changes

**Example:**

```bash
git commit -S -m "feat(auth): add two-factor authentication

Implements 2FA using TOTP tokens. Users can enable 2FA in their
profile settings.

Closes #123"
```

## Signing Commits

All commits must be signed with GPG. To set up commit signing:

```bash
# Generate a GPG key (if you don't have one)
gpg --gen-key

# List your GPG keys
gpg --list-secret-keys --keyid-format LONG

# Configure Git to use your key
git config --global user.signingkey <YOUR_KEY_ID>
git config --global commit.gpgSign true

# Add your GPG key to GitHub
gpg --armor --export <YOUR_KEY_ID>
# Copy the entire output (including the BEGIN and END PGP PUBLIC KEY BLOCK lines)
# and paste it into GitHub under Settings → SSH and GPG keys → New GPG key.
```

## Pull Request Guidelines

- **Keep PRs small:** Aim for < 600 lines of changes. Large PRs are harder to review.
- **Write clear descriptions:** Use the PR template and fill out all relevant sections.
- **Link related issues:** Reference issues with `Closes #123` or `Fixes #456`.
- **Ensure CI passes:** All checks must pass before merging.
- **Request reviews:** Tag relevant maintainers or wait for automatic review.
- **Address feedback:** Respond to review comments promptly.

## Code Style

- **Formatting:** We use Prettier for all code formatting. Run `npx prettier --write .` before committing.
- **Linting:** ESLint (JavaScript/TypeScript) and PHPStan (PHP) are enforced.
- **Testing:** All new features should include tests.

## REUSE Compliance

All files must include SPDX license headers. **SecPal uses different licenses depending on file type:**

### License Selection Guide

| File Type            | License             | Use For                                         |
| -------------------- | ------------------- | ----------------------------------------------- |
| **Application Code** | `AGPL-3.0-or-later` | PHP, TypeScript, JavaScript, React components   |
| **Configuration**    | `CC0-1.0`           | YAML, JSON, TOML, `.gitignore`, `.editorconfig` |
| **Helper Scripts**   | `MIT`               | Standalone bash/shell scripts, build utilities  |
| **Documentation**    | `CC0-1.0`           | Markdown files (except LICENSE itself)          |

### SPDX Header Examples

**For application code (AGPL-3.0-or-later):**

```php
<?php
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

```javascript
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

```typescript
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

**For configuration files (CC0-1.0):**

```yaml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: CC0-1.0
```

<!-- REUSE-IgnoreStart -->

```json
{
  "_comment": "SPDX-FileCopyrightText: 2025 SecPal Contributors",
  "_license": "SPDX-License-Identifier: CC0-1.0"
}
```

<!-- REUSE-IgnoreEnd -->

**For helper scripts (MIT):**

```bash
#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: MIT
```

**For documentation (CC0-1.0):**

```markdown
<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->
```

### Verification

Run `reuse lint` before committing to verify compliance:

```bash
# Check all files for REUSE compliance
reuse lint

# Add headers to new files automatically
reuse annotate --license AGPL-3.0-or-later --copyright "SecPal Contributors" path/to/file.php
```

### Bulk Licensing with REUSE.toml

For files that cannot contain comments (images, binaries, etc.) or to license entire directories, use `REUSE.toml` instead of the deprecated `.reuse/dep5`:

**Create `REUSE.toml` in root or subdirectories:**

<!-- REUSE-IgnoreStart -->

```toml
version = 1

# Example: License all images in assets directory
[[annotations]]
path = "assets/images/**"
precedence = "aggregate"
SPDX-FileCopyrightText = "2025 SecPal Contributors"
SPDX-License-Identifier = "CC0-1.0"

# Example: Override licensing for vendor/third-party code
[[annotations]]
path = ["vendor/**", "node_modules/**"]
precedence = "override"
SPDX-FileCopyrightText = "Various third-party contributors"
SPDX-License-Identifier = "SEE-LICENSE-IN-PACKAGE"
```

<!-- REUSE-IgnoreEnd -->

**Precedence options:**

- `closest` (default): Use file's own headers if present, fallback to REUSE.toml
- `aggregate`: Combine both file headers AND REUSE.toml information
- `override`: REUSE.toml takes precedence, ignore file headers

**Alternative for individual files:** Create adjacent `.license` files (e.g., `logo.png.license`) containing SPDX headers.

**How to choose the correct copyright attribution:**

- Use **"SecPal Contributors"** for all code files, including source code, test files, scripts, and any file where individual contributors make changes (e.g., `.js`, `.ts`, `.php`, `.py`, `.sh`, test files in any language).
- Use **"SecPal"** for organizational documentation (e.g., `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`), workflow files (e.g., `.github/workflows/*.yml`), and configuration files in the root directory (e.g., `.eslintrc.yml`, `.prettierrc`, `package.json`, `composer.json`, etc.).
- If a configuration file is specific to a code module or contains logic contributed by individuals, use **"SecPal Contributors"**.
- For ambiguous cases, prefer **"SecPal Contributors"** if the file is likely to be edited by multiple people over time.
- Use the **current year** in the copyright date (e.g., 2025 for files created in 2025).

Run `reuse lint` to check compliance.

## Getting Help

If you have questions or need help:

- Open a [Discussion](https://github.com/orgs/SecPal/discussions)
- Join our community channels (if available)
- Check existing issues and documentation

## License

By contributing to SecPal, you agree that your contributions will be licensed under the [AGPL-3.0-or-later](https://spdx.org/licenses/AGPL-3.0-or-later.html) license.

Thank you for contributing to SecPal! 🎉
