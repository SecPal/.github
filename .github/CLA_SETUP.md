<!--
SPDX-FileCopyrightText: 2025 SecPal

SPDX-License-Identifier: CC0-1.0
-->

# CLA Configuration

All SecPal repositories use [CLA Assistant](https://cla-assistant.io/) to ensure contributors sign the Contributor License Agreement.

## Setup Instructions

The CLA Assistant is configured via the hosted service at <https://cla-assistant.io/>

### Initial Configuration for New Repositories

1. **Sign in to CLA Assistant**
   - Visit <https://cla-assistant.io/>
   - Sign in with your GitHub account (requires admin access to SecPal organization)

2. **Configure Repository**
   - Click "Configure CLA"
   - Select the `SecPal/<repository>` repository
   - Link CLA document: `https://github.com/SecPal/.github/blob/main/CLA.md`
   - Save configuration

3. **Allowlist Configuration**
   - Add bot users to allowlist: `bot*`, `dependabot[bot]`, `dependabot-preview[bot]`
   - This allows automated PRs without CLA signature

### How It Works

- **New PRs**: CLA Assistant automatically comments on new pull requests from external contributors
- **Signing Process**: Contributors sign by commenting `I have read the CLA Document and I hereby sign the CLA`
- **Status Check**: PR status is updated once all contributors have signed
- **Re-signing**: Contributors must re-sign if the CLA document changes

### Required Branch Protection

Add the following status check to branch protection rules:

- `cla/check` - Ensures all contributors have signed the CLA

### Signature Storage

All signatures are stored in the CLA Assistant database (hosted by SAP). You can view and export signatures at <https://cla-assistant.io/>

## Repositories with CLA Enforcement

The following SecPal repositories are configured with CLA Assistant:

- `SecPal/contracts` - OpenAPI contracts repository

## References

- CLA Assistant: <https://github.com/cla-assistant/cla-assistant>
- CLA Document: <https://github.com/SecPal/.github/blob/main/CLA.md>
- CLA Assistant Service: <https://cla-assistant.io/>
