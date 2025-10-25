<!--
SPDX-FileCopyrightText: 2025 SecPal

SPDX-License-Identifier: CC0-1.0
-->

# Workflow Templates

This directory contains reusable GitHub Actions workflow templates for SecPal repositories.

## CLA Assistant (`cla.yml`)

Enforces CLA signatures for all pull requests. All SecPal repositories should include this workflow.

### Quick Setup

1. Copy `cla.yml` to your repository's `.github/workflows/` directory
2. Ensure `CLA_BOT_TOKEN` secret is configured (either organization-wide or per-repository)
3. Commit and push - the workflow will automatically run on new pull requests

### What it does

- Automatically checks if contributors have signed the CLA
- Posts helpful instructions for signing the CLA
- Stores all signatures centrally in `SecPal/.github` (branch: `cla-signatures`)
- Blocks merging until all contributors have signed

### Organization Secret (Recommended)

For organization-wide setup, add `CLA_BOT_TOKEN` as an organization secret:

1. Go to: <https://github.com/organizations/SecPal/settings/secrets/actions>
2. Click "New organization secret"
3. Name: `CLA_BOT_TOKEN`
4. Value: Personal Access Token with `repo` scope
5. Repository access: "All repositories" or select specific repos

This way, all repositories can use the same token without individual configuration.

## For More Information

- [CLA Document](../CLA.md)
- [Dual-Licensing Documentation](../README.md#licensing)
- [Contributing Guidelines](../CONTRIBUTING.md)
