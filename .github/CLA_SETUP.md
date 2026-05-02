<!--
SPDX-FileCopyrightText: 2025-2026 SecPal

SPDX-License-Identifier: CC0-1.0
-->

# CLA Configuration

All SecPal repositories use [CLA Assistant](https://cla-assistant.io/) to ensure contributors sign the Contributor License Agreement.

## Organization-Wide Setup (Recommended)

**CLA Assistant is configured at the organization level** for all SecPal repositories.

### Why Link the Organization?

When you link an organization with CLA Assistant:

- **Automatic Coverage**: CLA becomes active for all existing and future repositories in the organization
- **Centralized Management**: Single configuration point for all repositories
- **Webhooks**: CLA Assistant creates organization-level webhooks to listen to Pull Requests across all repos

### Initial Organization Configuration

1. **Sign in to CLA Assistant**

   - Visit <https://cla-assistant.io/>
   - Sign in with your GitHub account (requires **owner** access to SecPal organization)

2. **Link Organization**

   - Click "Link Organization" button
   - Grant CLA Assistant the required authorization scopes to create webhooks for the organization
   - Select `SecPal` organization

3. **Configure CLA**

   - Link CLA document: `https://github.com/SecPal/.github/blob/main/CLA.md`
   - Save configuration

4. **Allowlist Configuration**
   - Add bot users to allowlist: `bot*`, `dependabot[bot]`, `dependabot-preview[bot]`, `copilot-swe-agent`, `cursoragent`
   - This allows automated PRs without CLA signature
   - Copilot-created pull requests in SecPal currently appear as author `copilot-swe-agent`; keep that exact account in the allowlist alongside Dependabot
   - Cursor agent-assisted commits can appear in CLA Assistant as `cursoragent`; keep that exact account in the allowlist as well so bot-assisted PRs do not block on `cla/check`

### How It Works

- **New PRs**: CLA Assistant automatically comments on new pull requests from external contributors (in any SecPal repository)
- **Signing Process**: Contributors sign by commenting `I have read the CLA Document and I hereby sign the CLA`
- **Status Check**: PR status is updated once all contributors have signed
- **Re-signing**: Contributors must re-sign if the CLA document changes
- **Organization-Wide**: One signature applies to all SecPal repositories

### Required Verification

Changing the allowlist in documentation is not enough. Because CLA Assistant is an external service with live organization settings, verify the active configuration after setup changes.

Use this checklist:

1. Confirm the allowlist includes `dependabot[bot]`, `dependabot-preview[bot]`, `copilot-swe-agent`, and `cursoragent`
2. Confirm the organization or repository link still points to the current SecPal CLA document
3. Confirm the expected required status check is `cla/check`
4. Verify a recent automated PR shows `cla/check` passing instead of blocking on signature
5. If the live config does not match the documented setup, track that drift as a `.github` issue before closing the related repository-specific issue

### Required Branch Protection

Add the following status check to branch protection rules for each repository:

- `cla/check` - Ensures all contributors have signed the CLA

### Signature Storage

All signatures are stored in the CLA Assistant database (hosted by SAP). You can view and export signatures at <https://cla-assistant.io/>

## Alternative: Per-Repository Configuration

If organization-level linking is not desired, you can configure CLA Assistant for individual repositories by selecting specific repositories instead of linking the entire organization.
However, this requires manual configuration for each new repository.

## Active Repositories

The following SecPal repositories are automatically covered by the organization-wide CLA:

- `SecPal/contracts` - OpenAPI contracts repository
- All future SecPal repositories

## References

- CLA Assistant: <https://github.com/cla-assistant/cla-assistant>
- CLA Document: <https://github.com/SecPal/.github/blob/main/CLA.md>
- CLA Assistant Service: <https://cla-assistant.io/>
