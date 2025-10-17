<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal GitHub Configuration

This repository contains all GitHub-specific configuration and templates for the SecPal project.

## ⚠️ Important: Repository Structure

SecPal uses **separate repositories** for each component:

- `SecPal/api` - Laravel Backend
- `SecPal/frontend` - Frontend Application
- `SecPal/contracts` - TypeScript Contracts
- `SecPal/.github` - Shared GitHub Configuration (this repository)

## 🏗️ Workflows: Templates vs Active

This repository contains **two types** of workflows:

### Active Workflows (for this `.github` repository)

- ✅ `config-checks.yml` - Prettier formatting and REUSE compliance for configuration files

### Template Workflows (for other repositories)

The following workflows are **templates** that assume a monorepo structure with `./frontend`, `./api`, `./contracts` directories. **Copy them to individual repositories** and adjust the `working-directory` paths accordingly:

- `tests.yml` - Template for frontend/API/contracts tests
- `format.yml` - Template for Prettier (frontend) and Pint (API) formatting
- `reuse.yml` - Template for REUSE compliance (works without changes)
- `license-check.yml` - Template for license compatibility checks
- `signed-commits.yml` - Template for signed commit verification
- `security.yml` - Template for security scanning
- `dependency-review.yml` - Template for dependency review
- `labeler.yml` - Template for auto-labeling PRs
- `stale.yml` - Template for stale issue management
- `release.yml` - Template for release automation

**Example:** To use `tests.yml` in the `contracts` repository, remove the `working-directory: ./contracts` line since the repo root is the contracts directory.

## 📁 Structure

```
.github/
├── ISSUE_TEMPLATE/          # Issue templates
│   ├── bug_report.md        # Bug report template
│   ├── feature_request.md   # Feature request template
│   ├── documentation.yml    # Documentation issue template
│   └── config.yml           # Issue template configuration
├── workflows/               # GitHub Actions workflows
│   ├── config-checks.yml   # Active: Checks for this repo (Prettier, REUSE)
│   ├── tests.yml           # Template: Test suite
│   ├── format.yml          # Template: Code formatting checks
│   ├── reuse.yml           # Template: REUSE compliance check
│   ├── license-check.yml   # Template: License compatibility check
│   ├── signed-commits.yml  # Template: Verify signed commits
│   ├── security.yml        # Template: Security scanning
│   ├── dependency-review.yml # Template: Dependency review
│   ├── labeler.yml         # Template: Auto-label PRs
│   ├── stale.yml           # Template: Stale issue management
│   └── release.yml         # Template: Release automation
├── BRANCH_PROTECTION.md     # Branch protection rules
├── branch-protection-*.json # Branch protection configs
├── CODE_OF_CONDUCT.md      # Community code of conduct
├── CODEOWNERS              # Code ownership definitions
├── CONTRIBUTING.md         # Contribution guidelines
├── dependabot.yml          # Dependabot configuration
├── FUNDING.yml             # Funding information
├── labeler.yml             # PR labeling rules
├── pull_request_template.md # PR template
├── SECURITY.md             # Security policy
├── SUPPORT.md              # Support resources
└── _config.yml             # GitHub Pages config
```

## 🔄 Workflows

### CI/CD Pipelines

All pull requests must pass the following checks:

#### Required Checks

- ✅ **Tests** - All unit and integration tests must pass
- ✅ **Code Formatting** - Prettier (frontend) and Pint (API) checks
- ✅ **REUSE Compliance** - All files must have proper SPDX headers
- ✅ **License Check** - Dependencies must be AGPL-compatible
- ✅ **Signed Commits** - All commits must be GPG/SSH signed
- ✅ **Security Scan** - CodeQL and dependency audits

#### Automated Workflows

- 🏷️ **Auto-labeling** - PRs are automatically labeled based on changed files
- 🕐 **Stale Management** - Inactive issues/PRs are marked and closed
- 📦 **Dependency Review** - New dependencies are reviewed for security/licensing

### Workflow Schedule

- **Tests**: On every push and PR
- **Security Scan**: Weekly on Mondays at 6:00 AM UTC
- **Stale Check**: Daily at 1:00 AM UTC
- **Dependabot**: Every Friday at 9:00 AM Europe/Berlin

## 🛡️ Branch Protection

### Main Branch

The `main` branch is protected with:

- **No review requirements** (single maintainer)
- **Signed commits only**
- **All CI checks must pass**
- **Linear history** (no merge commits)
- **No force pushes**
- **No direct commits** (PR only)

See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) for complete rules and setup instructions.

**Note**: Branch protection is applied to each repository individually (api, frontend, contracts, .github).

## � Required Secrets

### SYNC_TOKEN

The automated template synchronization workflow (`sync-templates.yml`) requires a `SYNC_TOKEN` secret with the following permissions:

- `contents: write` - To push changes to target repositories
- `pull-requests: write` - To create pull requests in target repositories

**Setup Instructions:**

1. Create a GitHub Personal Access Token (Classic) or Fine-Grained Token
2. For Classic Token: Select scopes `repo` (full control)
3. For Fine-Grained Token: Grant permissions `contents: write` and `pull-requests: write` for target repositories
4. Add the token as a secret named `SYNC_TOKEN` in this repository's settings

**Why not GITHUB_TOKEN?**

The default `GITHUB_TOKEN` only has permissions for the current repository. Cross-repository operations (creating PRs in `contracts`, `api`, etc.) require a Personal Access Token with broader scope.

## �📝 Issue & PR Templates

### Creating Issues

Use the appropriate template:

- **Bug Report**: For reporting bugs
- **Feature Request**: For suggesting features
- **Documentation**: For documentation improvements

### Creating Pull Requests

The PR template includes:

- Summary and related issues
- Type of change checklist
- Testing verification
- Code quality checklist
- Legal compliance verification

## 👥 Code Owners

Code ownership is defined in [CODEOWNERS](CODEOWNERS):

- `@SecPal/maintainers` - Overall project
- `@SecPal/frontend-team` - Frontend code
- `@SecPal/backend-team` - API code
- `@SecPal/contracts-team` - Contracts code
- `@SecPal/security-team` - Security-related files

## 🤝 Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines including:

- Development setup
- Commit conventions
- Code style guidelines
- Testing requirements
- PR submission process

## 🔒 Security

Security is critical for SecPal. Please:

- Read our [Security Policy](SECURITY.md)
- Report vulnerabilities to **security@sepal.app**
- **Never** report security issues publicly

## 📄 License

This project is licensed under **AGPL-3.0-or-later**.

All files must include SPDX headers:

```
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
```

## 🆘 Support

Need help? Check out:

- [Support Documentation](SUPPORT.md)
- Issue trackers in individual repositories:
  - [API Issues](https://github.com/SecPal/api/issues)
  - [Frontend Issues](https://github.com/SecPal/frontend/issues)
  - [Contracts Issues](https://github.com/SecPal/contracts/issues)

## 📊 Status Badges

Add these to your repository READMEs (replace `REPO` with `api`, `frontend`, or `contracts`):

```markdown
[![Tests](https://github.com/SecPal/REPO/workflows/Tests/badge.svg)](https://github.com/SecPal/REPO/actions/workflows/tests.yml)
[![REUSE status](https://api.reuse.software/badge/github.com/SecPal/REPO)](https://api.reuse.software/info/github.com/SecPal/REPO)
[![Security](https://github.com/SecPal/REPO/workflows/Security%20Scanning/badge.svg)](https://github.com/SecPal/REPO/actions/workflows/security.yml)
```

## 🔧 Maintenance

### Regular Tasks

- Review and merge Dependabot PRs
- Triage new issues weekly
- Review stale issues monthly
- Update branch protection as needed
- Monitor security advisories

### Updating Workflows

When updating workflows:

1. Test in a feature branch first
2. Verify all jobs complete successfully
3. Update documentation if needed
4. Get review from maintainers

---

**For questions about GitHub configuration, please contact the maintainers.**
