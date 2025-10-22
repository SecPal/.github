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

1. **Clone the repository:**

   ```bash
   git clone https://github.com/SecPal/<repository>.git
   cd <repository>
   ```

2. **Set up Git hooks (automatic):**

   Git hooks are automatically configured via `.githooks/` directory:

   ```bash
   git config core.hooksPath .githooks
   ```

3. **Install pre-commit (optional, for additional checks):**

   ```bash
   # Install pre-commit
   pip install pre-commit
   # or: brew install pre-commit

   # Install hooks
   pre-commit install
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
- PR size (< 600 lines recommended)

## How to Contribute

1. **Fork the repository** and create a new branch from `main`.
2. **Create a feature branch** using our naming convention (see below).
3. **Write your code** and add tests where applicable.
4. **Ensure all tests pass** locally by running `./scripts/preflight.sh`.
5. **Sign your commits** with GPG (see below).
6. **Push your branch** and open a pull request against `main`.

All pull requests will be reviewed by a maintainer and by GitHub Copilot.

## Branch Naming Convention

Use the following prefixes for your branch names:

- `feat/` - New features (e.g., `feat/add-user-profile`)
- `fix/` - Bug fixes (e.g., `fix/login-redirect`)
- `chore/` - Maintenance tasks (e.g., `chore/update-dependencies`)
- `docs/` - Documentation changes (e.g., `docs/update-readme`)
- `refactor/` - Code refactoring (e.g., `refactor/simplify-auth`)
- `test/` - Test additions or fixes (e.g., `test/add-e2e-tests`)

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
# Then add it at: https://github.com/settings/keys
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

All files must include SPDX license headers:

```php
<?php
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

```javascript
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

```markdown
<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->
```

Run `reuse lint` to check compliance.

## Getting Help

If you have questions or need help:

- Open a [Discussion](https://github.com/orgs/SecPal/discussions)
- Join our community channels (if available)
- Check existing issues and documentation

## License

By contributing to SecPal, you agree that your contributions will be licensed under the [AGPL-3.0-or-later](https://spdx.org/licenses/AGPL-3.0-or-later.html) license.

Thank you for contributing to SecPal! 🎉
