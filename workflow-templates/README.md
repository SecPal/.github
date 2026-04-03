<!--
SPDX-FileCopyrightText: 2025 SecPal

SPDX-License-Identifier: CC0-1.0
-->

# Workflow Templates

This directory contains reusable GitHub Actions workflow templates for SecPal repositories.

## CLA Assistant

**Note:** SecPal uses a repo-local GitHub Actions workflow for CLA management. Every protected repository should carry `.github/workflows/license-cla.yml` on its default branch.

### How The CLA Workflow Works

1. **Automatic PR Checks**: The repo-local workflow evaluates every non-exempt contributor on pull request events
2. **Comment-Based Signing**: Missing contributors sign by adding the exact pull request comment `I have read the CLA and I hereby sign it.`
3. **Deterministic Status**: The workflow updates the `license/cla` commit status directly instead of depending on an external webhook
4. **Repo-Local Storage**: Signature metadata is written to `signatures/version1/cla.json` on the `cla-signatures` branch

### For Repository Maintainers

Every protected repository should:

- carry `.github/workflows/license-cla.yml` on the default branch
- keep the shared CLA document link pointing to `SecPal/.github`
- add `license/cla` to required status checks after the workflow is live on `main`
- allow the workflow to manage the `cla-signatures` branch

### Adding CLA to a New Repository

1. Copy `.github/workflows/license-cla.yml` into the repository
2. Merge it to the default branch
3. Run `.github/scripts/enable-cla-required-checks.sh` from this repository
4. Verify that `license/cla` appears on new pull requests

The old hosted `CLA Assistant` integration is intentionally no longer used for required status enforcement.

## For More Information

- [CLA Document](../CLA.md)
- [Dual-Licensing Documentation](../README.md#licensing)
- [Contributing Guidelines](../CONTRIBUTING.md)
