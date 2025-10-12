<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Contributing to SecPal

First off, thank you for considering contributing to SecPal! It's people like you that make SecPal a great tool for private security services.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Commit Guidelines](#commit-guidelines)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [License](#license)

## 📜 Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## 🚀 Getting Started

### Where do I go from here?

1. **Check existing issues**: Look through existing issues in the relevant repository:
   - [API Issues](https://github.com/SecPal/api/issues)
   - [Frontend Issues](https://github.com/SecPal/frontend/issues)
   - [Contracts Issues](https://github.com/SecPal/contracts/issues)
2. **Create an issue**: If not found, create a new issue in the appropriate repository
3. **Get feedback**: Wait for maintainer feedback before starting significant work

### Types of Contributions

We welcome:

- 🐛 Bug fixes
- ✨ New features
- 📝 Documentation improvements
- 🌐 Translations
- ✅ Tests
- 🎨 UI/UX improvements

## 💻 Development Setup

### Prerequisites

- **DDEV**: Local development environment
- **Node.js 22+**: For frontend and contracts
- **PHP 8.4+**: For Laravel API
- **PostgreSQL 16+**: Database
- **Git**: With GPG/SSH signing configured

### Local Setup

```bash
# Clone the repositories you want to work on
git clone https://github.com/YOUR_USERNAME/api.git SecPal-api
git clone https://github.com/YOUR_USERNAME/frontend.git SecPal-frontend
git clone https://github.com/YOUR_USERNAME/contracts.git SecPal-contracts

# Add upstream remotes
cd SecPal-api
git remote add upstream https://github.com/SecPal/api.git

cd ../SecPal-frontend
git remote add upstream https://github.com/SecPal/frontend.git

cd ../SecPal-contracts
git remote add upstream https://github.com/SecPal/contracts.git

# Start DDEV (from the api directory)
cd ../SecPal-api
ddev start

# Install frontend dependencies
cd frontend
npm install

# Install API dependencies
cd ../api
composer install

# Install contracts dependencies
cd ../contracts
npm install
```

### Configure Git Signing

All commits must be signed. Configure your Git:

```bash
# For GPG signing
git config --global commit.gpgsign true
git config --global user.signingkey YOUR_GPG_KEY_ID

# For SSH signing
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
```

See [GitHub's guide on signing commits](https://docs.github.com/en/authentication/managing-commit-signature-verification).

## 🔨 Making Changes

### Fork & Create a Branch

1. Fork SecPal to your GitHub account
2. Create a feature branch from `main`:

```bash
git checkout -b 123-descriptive-feature-name
```

Good branch naming convention: `issue-number-brief-description`

Examples:

- `42-add-offline-sync`
- `128-fix-login-bug`
- `256-update-german-translations`

### Development Workflow

1. **Make your changes**: Write clean, documented code
2. **Test locally**: Run all tests and verify functionality
3. **Format code**: Run Prettier and Pint
4. **Commit changes**: Use signed commits with clear messages
5. **Push to your fork**: Keep your branch up to date

## 📝 Commit Guidelines

### Commit Messages

Follow conventional commits:

```
type(scope): brief description

Detailed explanation of what and why (not how).

Fixes #123
```

**Types**:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Test updates
- `chore`: Build/tooling changes
- `perf`: Performance improvements
- `security`: Security fixes

**Examples**:

```
feat(frontend): add offline data sync

Implements IndexedDB storage for offline-first functionality.
Data is synced automatically when connection is restored.

Fixes #123
```

```
fix(api): resolve authentication token expiry issue

Tokens were expiring too quickly due to incorrect timezone handling.
Now correctly using UTC for all token operations.

Fixes #456
```

### Signed Commits

All commits MUST be signed:

```bash
git commit -S -m "feat: add new feature"
```

Or configure automatic signing (recommended):

```bash
git config commit.gpgsign true
```

## 🎨 Code Style

### Frontend (React/TypeScript)

- Use **Prettier** for formatting
- Follow React best practices
- Use TypeScript strictly
- Mobile-first responsive design

```bash
cd frontend
npm run format
npm run lint
```

### Backend (Laravel/PHP)

- Use **Laravel Pint** for formatting
- Follow PSR-12 standards
- Use type hints

```bash
cd api
./vendor/bin/pint
```

### General Guidelines

- Write self-documenting code
- Add comments for complex logic
- Keep functions small and focused
- Follow SOLID principles
- Mobile first, offline first!

## ✅ Testing

### Run Tests

```bash
# Frontend tests
cd frontend
npm test

# API tests
cd api
php artisan test

# Contracts tests
cd contracts
npm test
```

### Writing Tests

- Write tests for new features
- Ensure bug fixes include regression tests
- Aim for high test coverage
- Test offline functionality
- Test mobile responsiveness

## 🚀 Submitting Changes

### Pre-Commit Workflow (CRITICAL)

**MANDATORY steps before EVERY commit - NO EXCEPTIONS:**

```bash
# 1. Check current status
git status

# 2. Review all changes - ensure ALL are intentional
git diff

# 3. Run local validation (see commands below)
npm run check  # Quick validation
# or
npm run check:full  # Complete validation including licenses

# 4. Check status again - did tests modify files?
git status

# 5. If tests changed files: review and stage them
git diff
git add <modified-files>

# 6. Commit with signed commit
git commit -S -m "type(scope): description"

# 7. FINAL CHECK - must be clean before push
git status

# 8. Only push if working tree is clean
git push
```

### Local CI/CD Validation Commands

Run these **before every commit** to catch issues locally:

```bash
# Quick validation (most common checks)
npm run format:check      # Code formatting
npm test                  # Unit/integration tests
npm run validate          # Linting, OpenAPI validation
npm run build             # TypeScript compilation

# Security & Compliance
npm audit --production    # Dependency vulnerabilities
npx reuse lint            # SPDX header compliance

# License compatibility (requires .license-policy.json)
# See scripts/check-licenses.sh for automated checking
./scripts/check-licenses.sh
```

**Recommended: Add to `package.json`:**

```json
{
  "scripts": {
    "check": "npm run format:check && npm test && npm run validate && npm run build && npm audit --production && npx reuse lint",
    "check:full": "npm run check && ./scripts/check-licenses.sh"
  }
}
```

Then simply run:

```bash
npm run check       # Fast pre-commit validation
npm run check:full  # Complete validation
```

**Why this matters:**

- Catches ~90% of CI failures before push
- Faster iteration - fix issues immediately
- No waiting for CI to fail
- Cleaner git history

> 📚 **For detailed explanations and troubleshooting**, see [Lessons Learned](docs/LESSONS-LEARNED-CONTRACTS-REPO.md#11-inconsistent-pre-commit-validation)

### Before Submitting

Ensure:

- [ ] All tests pass locally (`npm run check`)
- [ ] Code is formatted (Prettier/Pint)
- [ ] Commits are signed (`git log --show-signature -1`)
- [ ] REUSE compliance (`npx reuse lint`)
- [ ] Documentation is updated
- [ ] No new security vulnerabilities (`npm audit`)
- [ ] License compatibility verified

### Create Pull Request

1. **Push your changes**:

```bash
git push origin 123-descriptive-feature-name
```

2. **Open a Pull Request** on GitHub
3. **Fill out the PR template** completely
4. **Link related issues**
5. **Wait for CI checks** to pass
6. **Respond to review feedback**

### Keeping Your PR Updated

If the main branch has moved forward:

```bash
git fetch upstream
git rebase upstream/main
git push --force-with-lease origin 123-descriptive-feature-name
```

### Review Process

- The maintainer will review your PR
- May request changes or ask questions
- Be patient and responsive
- CI must pass before merging

## 📄 License

### REUSE Compliance

All source files must include SPDX headers:

```
// SPDX-FileCopyrightText: 2025 SecPal Contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
```

### Contribution Agreement

By contributing to SecPal, you agree that:

- Your contributions will be licensed under **AGPL-3.0-or-later**
- You have the right to submit the code
- Your commits are signed and verified
- You comply with all licensing requirements

### Dependency Licenses

When adding dependencies, verify they are compatible with AGPL-3.0-or-later:

**Compatible licenses**:

- MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause
- ISC, 0BSD, CC0-1.0, Unlicense
- GPL-3.0, LGPL-3.0, AGPL-3.0

**Incompatible licenses**:

- Proprietary
- GPL-2.0 (without "or later")
- Non-commercial licenses

## 🆘 Getting Help

- � Check the [SUPPORT.md](SUPPORT.md) for support resources
- 🐛 Issue Trackers:
  - [API Issues](https://github.com/SecPal/api/issues)
  - [Frontend Issues](https://github.com/SecPal/frontend/issues)
  - [Contracts Issues](https://github.com/SecPal/contracts/issues)

## 🎉 Thank You!

Your contributions make SecPal better for everyone. We appreciate your time and effort!

---

**Happy Contributing! 🚀**
