<!--
SPDX-FileCopyrightText: 2025 SecPal

SPDX-License-Identifier: CC0-1.0
-->

# Workflow Templates

This directory contains reusable GitHub Actions workflow templates for SecPal repositories.

## CLA Assistant

**Note:** SecPal uses the hosted [CLA Assistant service](https://cla-assistant.io/) for CLA management. This is configured organization-wide and does **not** require workflow files in individual repositories.

### How CLA Assistant Works

1. **Automatic PR Comments**: When a contributor opens a pull request, CLA Assistant automatically posts a comment
2. **Click-Through Signing**: Contributors click the link to sign the CLA on [cla-assistant.io](https://cla-assistant.io/)
3. **OAuth Authentication**: GitHub OAuth ensures secure identity verification
4. **Status Updates**: PR status is automatically updated when all contributors have signed
5. **Centralized Management**: All signatures are stored in a database (Azure Europe, GDPR-compliant)

### For Repository Maintainers

**No setup required!** CLA Assistant is configured at the organization level:

- CLA document: Stored as a GitHub Gist and linked on [cla-assistant.io](https://cla-assistant.io/)
- All repositories automatically protected
- Contributors sign via <https://cla-assistant.io/>
- Signatures are centrally managed

### Adding CLA to a New Repository

1. Go to [cla-assistant.io](https://cla-assistant.io/) (sign in with GitHub)
2. Select your new repository
3. Link it to the organization's CLA Gist
4. Done! CLA Assistant will now monitor all pull requests

**No workflow files needed** - CLA Assistant uses GitHub webhooks directly.

## For More Information

- [CLA Document](../CLA.md)
- [CLA Assistant Service](https://cla-assistant.io/)
- [CLA Assistant Documentation](https://github.com/cla-assistant/cla-assistant)
- [Dual-Licensing Documentation](../README.md#licensing)
- [Contributing Guidelines](../CONTRIBUTING.md)
