<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal GitHub Configuration

This directory contains all GitHub-specific configuration and templates for the SecPal project.

## 📁 Structure

```
.github/
├── ISSUE_TEMPLATE/          # Issue templates
│   ├── bug_report.md        # Bug report template
│   ├── feature_request.md   # Feature request template
│   ├── documentation.yml    # Documentation issue template
│   └── config.yml           # Issue template configuration
├── workflows/               # GitHub Actions workflows
│   ├── tests.yml           # Test suite
│   ├── format.yml          # Code formatting checks
│   ├── reuse.yml           # REUSE compliance check
│   ├── license-check.yml   # License compatibility check
│   ├── signed-commits.yml  # Verify signed commits
│   ├── security.yml        # Security scanning
│   ├── dependency-review.yml # Dependency review
│   ├── labeler.yml         # Auto-label PRs
│   └── stale.yml           # Stale issue management
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

- **2 required reviewers**
- **Signed commits only**
- **All CI checks must pass**
- **Linear history** (no merge commits)
- **No force pushes**
- **No direct commits** (PR only)

See [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) for complete rules.

### Setting Up Protection

```bash
# Apply main branch protection
gh api repos/SecPal/SecPal/branches/main/protection \
  --method PUT \
  --input .github/branch-protection-main.json
```

## 📝 Issue & PR Templates

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
- Report vulnerabilities via [GitHub Security Advisories](https://github.com/SecPal/SecPal/security/advisories/new)
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
- [GitHub Discussions](https://github.com/SecPal/SecPal/discussions)
- [Issue Tracker](https://github.com/SecPal/SecPal/issues)

## 📊 Status Badges

Add these to your README:

```markdown
[![Tests](https://github.com/SecPal/SecPal/workflows/Tests/badge.svg)](https://github.com/SecPal/SecPal/actions/workflows/tests.yml)
[![REUSE status](https://api.reuse.software/badge/github.com/SecPal/SecPal)](https://api.reuse.software/info/github.com/SecPal/SecPal)
[![Security](https://github.com/SecPal/SecPal/workflows/Security%20Scanning/badge.svg)](https://github.com/SecPal/SecPal/actions/workflows/security.yml)
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
