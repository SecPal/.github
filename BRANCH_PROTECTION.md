# SPDX-FileCopyrightText: 2025 SecPal Contributors

# SPDX-License-Identifier: AGPL-3.0-or-later

# Branch Protection Rules

This document describes the branch protection rules that should be configured for the SecPal repositories.

**Note**: As this is currently a single-maintainer project, review requirements are disabled. They can be enabled later when the team grows.

## Main Branch Protection

The `main` branch should have the following protections enabled:

### Status Checks

- ✅ Require status checks to pass before merging
- ✅ Require branches to be up to date before merging

Required status checks:

- `Tests / frontend-tests`
- `Tests / api-tests`
- `Tests / contracts-tests`
- `Code Formatting / prettier`
- `Code Formatting / pint`
- `REUSE Compliance Check / reuse`
- `License Compatibility Check / check-npm-licenses`
- `License Compatibility Check / check-composer-licenses`
- `Verify Signed Commits / verify-commits`

### Commit Signing

- ✅ Require signed commits
- All commits must be signed with a verified GPG or SSH key

### Other Settings

- ✅ Require linear history (no merge commits, use rebase or squash)
- ✅ Allow force pushes: **Disabled**
- ✅ Allow deletions: **Disabled**

## Develop Branch Protection

The `develop` branch should have similar protections:

### Status Checks

Same as main branch, except:

- `Verify Signed Commits / verify-commits` is optional for develop

### Other Settings

Same as main branch

## Setting up Branch Protection

To configure these rules via GitHub CLI:

```bash
# For main branch
gh api repos/SecPal/SecPal/branches/main/protection \
  --method PUT \
  --input branch-protection-main.json

# For develop branch
gh api repos/SecPal/SecPal/branches/develop/protection \
  --method PUT \
  --input branch-protection-develop.json
```

See the JSON configuration files in this directory for the exact settings.
