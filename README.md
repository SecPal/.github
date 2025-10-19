<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Organization

This repository contains general project documentation, settings, and community health files for the [SecPal organization](https://github.com/SecPal).

## About SecPal

SecPal is a digital guard book and much more. It's the "guard's friend" in every respect. The target group is private, German security services.

## Repositories

- [`.github`](https://github.com/SecPal/.github): Organization-wide settings and documentation.
- [`frontend`](https://github.com/SecPal/frontend): The SecPal frontend.
- [`api`](https://github.com/SecPal/api): The SecPal backend.
- [`contracts`](https://github.com/SecPal/contracts): OpenAPI contracts.

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
- Prettier formatting (Markdown, YAML, JSON)
- Markdownlint
- yamllint
- actionlint (GitHub Actions workflows)
- ShellCheck (shell scripts)
- File size limits
- Trailing whitespace
- Line ending normalization

## License

All projects within the SecPal organization are licensed under the [AGPL-3.0-or-later](https://spdx.org/licenses/AGPL-3.0-or-later.html).
