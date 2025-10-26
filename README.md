<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Organization

This repository contains general project documentation, settings, and community health files for the [SecPal organization](https://github.com/SecPal).

## About SecPal

SecPal is a digital guard book and much more. It's the "guard's friend" in every respect. The target group is private, German security services.

## Repositories

- [`.github`](https://github.com/SecPal/.github): Organization-wide settings and documentation
- [`contracts`](https://github.com/SecPal/contracts): OpenAPI 3.1 API specifications
- [`frontend`](https://github.com/SecPal/frontend): React/TypeScript frontend application
- `api`: The SecPal Laravel backend (planned)

## Development Setup

### Pre-commit Hooks

We use pre-commit hooks to ensure code quality before commits are made. This catches issues locally before CI/CD runs.

**Installation:**

```bash
# Install pre-commit (if not already installed)
pip install pre-commit
# or: brew install pre-commit

# Run the setup script
./scripts/setup-pre-commit.sh
```

**Manual Usage:**

```bash
# Run all hooks manually
pre-commit run --all-files

# Update hooks to latest versions
pre-commit autoupdate
```

**Included Checks:**

- REUSE 3.3 compliance

### Pre-push Hooks

We use a pre-push hook to run comprehensive quality checks before pushing to GitHub. This includes formatting, linting, testing, and PR size checks.

**Installation:**

The pre-push hook is already configured in `.githooks/pre-push` (version controlled). To enable it:

```bash
# Configure Git to use .githooks directory
git config core.hooksPath .githooks
```

Or run the setup script:

```bash
./scripts/setup-pre-push.sh
```

**What it checks:**

- Code formatting (Prettier, markdownlint)
- REUSE 3.3 compliance
- Workflow linting (actionlint - **disabled locally**, runs in CI only due to network timeout issues)
- Language-specific checks:
  - **PHP/Laravel**: Pint, PHPStan, tests
  - **Node.js**: ESLint, TypeScript, tests, npm audit
  - **OpenAPI**: Spectral/Redocly linting
- PR size limit (600 lines, configurable with `.preflight-allow-large-pr`)

**Manual Usage:**

```bash
# Run preflight checks manually
./scripts/preflight.sh

# Skip checks (not recommended)
git push --no-verify
```

**Included Checks (pre-commit):**

- Prettier formatting (Markdown, YAML, JSON)
- Markdownlint
- yamllint
- actionlint (GitHub Actions workflows)
- ShellCheck (shell scripts)
- File size limits
- Trailing whitespace
- Line ending normalization

## Build & Test Commands

Quick reference commands for local development across SecPal projects.

### PHP/Laravel Backend

```bash
# Dependencies
composer install --no-interaction --no-progress --prefer-dist --optimize-autoloader

# Code Style Check
./vendor/bin/pint --test

# Static Analysis
./vendor/bin/phpstan analyse --level=max

# Tests (parallel)
php artisan test --parallel
```

### Node.js/React Frontend

```bash
# Dependencies (use exact versions)
npm ci
# or for pnpm projects:
pnpm install --frozen-lockfile

# Linting
npm run lint

# Type Checking
npm run typecheck
# or:
npx tsc --noEmit

# Tests
npm test
# or:
pnpm test
```

### OpenAPI Validation

```bash
# Lint OpenAPI spec
npx @stoplight/spectral-cli lint docs/openapi.yaml
```

### Code Formatting (all files)

```bash
# Check formatting
npx prettier --check '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'

# Auto-fix
npx prettier --write '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}'
```

### REUSE Compliance

```bash
# Install REUSE tool
pip install reuse

# Validate compliance
reuse lint

# Add missing headers
reuse annotate --copyright "SecPal" --license "AGPL-3.0-or-later" <file>
```

## License

### Dual-Licensing Model

SecPal projects use a **dual-licensing** model:

#### 1. Open Source License (AGPL-3.0-or-later)

All projects are licensed under the [AGPL-3.0-or-later](LICENSES/AGPL-3.0-or-later.txt) for:

- ✅ **Open source projects** that comply with AGPL terms
- ✅ **Personal use** and experimentation
- ✅ **Educational purposes**
- ✅ **Community contributions**

**Key AGPL Requirements:**

- Distribute source code to users (including network users)
- Share modifications under AGPL
- Preserve copyright and license notices

#### 2. Commercial License

For use cases **incompatible with AGPL**, we offer commercial licenses that allow:

- ❌ **No requirement** to disclose source code
- ❌ **No copyleft obligations** for your applications
- ✅ **Proprietary** product integration
- ✅ **SaaS** offerings without AGPL compliance
- ✅ **Commercial support** and maintenance

**Interested in a commercial license?** Contact us at [legal@secpal.app](mailto:legal@secpal.app)

---

### Contributing

By contributing to SecPal projects, you agree to our [Contributor License Agreement (CLA)](CLA.md), which:

- Grants us rights to distribute your contributions under **both** licensing models
- Allows you to **retain copyright** ownership
- Ensures your work can benefit both open source and commercial users

**CLA Signing Process:**

When you submit your first pull request, [CLA Assistant](https://cla-assistant.io/) will automatically comment with instructions. Simply:

1. Click the link in the comment
2. Sign in with GitHub (OAuth)
3. Click "I agree" to sign the CLA
4. Your PR status will update automatically

All signatures are stored securely in a GDPR-compliant database hosted in Europe.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

### For Repository Maintainers

To enable CLA checks in your SecPal repository:

1. Go to [CLA Assistant](https://cla-assistant.io/) and sign in with GitHub
2. Click "Configure CLA"
3. Select your repository from the dropdown
4. Link it to the SecPal CLA Gist (ask an organization admin for the Gist URL)
5. Done! CLA Assistant will automatically monitor all pull requests

**Unlike the previous GitHub Action approach, no workflow files are needed** – CLA Assistant uses GitHub webhooks directly.

All CLA signatures are stored centrally in a secure database (Azure Europe, GDPR-compliant).

---

For full license information, see the [LICENSES](LICENSES/) directory.
