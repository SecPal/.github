<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Workspace

This is the multi-repository workspace for the SecPal project.

## Repository Structure

```
SecPal/
├── .github/       # Organization-wide settings and documentation
│   └── setup-hooks.sh  # Master script to setup hooks in all repos
├── api/           # Laravel backend API
├── contracts/     # OpenAPI 3.1 API specifications
└── frontend/      # React/TypeScript frontend application
```

## Quick Setup

After cloning all repositories, run the master setup script from the `.github` repository:

```bash
cd .github
./setup-hooks.sh
```

This will:

- Install pre-commit (if not already installed)
- Set up pre-commit hooks in all repos (formatting, linting, REUSE compliance)
- Set up pre-push hooks in all repos (comprehensive quality checks)

## Individual Repository Setup

If you need to set up hooks for a specific repository:

```bash
cd <repository>

# Install pre-commit (if not already installed)
pip install --user pre-commit

# Install pre-commit hooks
./scripts/setup-pre-commit.sh

# Install pre-push hooks
./scripts/setup-pre-push.sh
```

## Hook Architecture

SecPal uses two types of Git hooks:

### Pre-commit Hooks

- Managed by the [Python pre-commit framework](https://pre-commit.com/)
- Runs on every `git commit`
- Checks: Prettier, markdownlint, yamllint, actionlint, ShellCheck, REUSE compliance
- Configuration: `.pre-commit-config.yaml` in each repo

### Pre-push Hooks

- Implemented as symlinks to `scripts/preflight.sh`
- Runs on every `git push`
- Comprehensive checks including:
  - All pre-commit checks
  - Language-specific linting and type checking
  - Tests (where applicable)
  - PR size limits
  - Protection against pushing directly to main/master branches

## Bypassing Hooks (Emergencies Only)

```bash
git commit --no-verify  # Skip pre-commit
git push --no-verify    # Skip pre-push
```

**⚠️ Only use in emergencies!** Always follow up with a PR to fix any issues.

## Documentation

- [Git Hook Setup & Troubleshooting](.github/docs/HOOK_SETUP_TROUBLESHOOTING.md)
- [Contributing Guidelines](.github/CONTRIBUTING.md)
- [Development Workflow](.github/README.md)

## License

This project is licensed under AGPL-3.0-or-later. See individual repositories for detailed license information.
