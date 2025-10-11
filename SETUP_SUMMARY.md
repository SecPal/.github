<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal GitHub Setup - Summary

Complete documentation of the GitHub configuration for the SecPal project.

## Files Created

All GitHub configuration files have been created with SPDX headers and are REUSE compliant.

### Workflows (10)

- tests.yml - Unit and integration tests
- format.yml - Code formatting checks
- reuse.yml - REUSE compliance
- license-check.yml - License compatibility
- signed-commits.yml - Commit signing verification
- security.yml - Security scanning
- dependency-review.yml - Dependency review
- labeler.yml - Auto-labeling PRs
- stale.yml - Stale issue/PR management
- release.yml - Release automation

### Templates

- Bug report template
- Feature request template
- Documentation issue template
- Pull request template

### Documentation

- CONTRIBUTING.md - Contribution guidelines
- SECURITY.md - Security policy
- SUPPORT.md - Support resources
- CODE_OF_CONDUCT.md - Community guidelines
- BRANCH_PROTECTION.md - Branch protection rules
- README.md - GitHub configuration overview
- CODEOWNERS - Code ownership

### Configuration

- dependabot.yml - Dependency updates (Fridays 09:00 Europe/Berlin)
- labeler.yml - Auto-labeling rules
- branch-protection-main.json - Main branch rules
- branch-protection-develop.json - Develop branch rules

## Key Features

### CI/CD

- All workflows use latest versions (Node 22, PHP 8.4, PostgreSQL 16)
- Comprehensive test coverage
- Code formatting enforcement
- License compliance checks
- Security scanning (CodeQL, npm audit, composer audit)

### Branch Protection

- All CI checks required
- Signed commits enforced
- Linear history required
- No review requirements (single maintainer setup)

### Automation

- Dependabot updates every Friday
- Auto-labeling based on file changes
- Stale issue/PR management
- Automated releases on tags

## Next Steps

1. Review FUNDING.yml and add payment information
2. Adjust CODEOWNERS team names if needed
3. Create repository on GitHub
4. Push code and apply branch protection
5. Create labels for automation

For detailed information, see the individual documentation files.
