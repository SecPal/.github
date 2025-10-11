<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Security Policy

## Supported Versions

We are committed to ensuring the security of SecPal. Below are the versions of our project that are currently being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x   | :white_check_mark: |

**Note**: SecPal is currently in early development (pre-1.0). We are starting with version 0.0.1 and will provide security updates for the latest 0.x.x release.

## Reporting a Vulnerability

We take all security bugs in SecPal seriously. Thank you for improving the security of our project. We appreciate your efforts and responsible disclosure and will make every effort to acknowledge your contributions.

### How to Report

**Please do not report security vulnerabilities through public GitHub issues!**

To report a security vulnerability, please email: **security@sepal.app**

### What to Include

Please include the requested information listed below (as much as you can provide) to help us better understand the nature and scope of the possible issue:

- **Type of issue** (e.g. buffer overflow, SQL injection, cross-site scripting, authentication bypass, etc.)
- **Full paths of source file(s)** related to the manifestation of the vulnerability
- **Location of the affected source code** (tag/branch/commit or direct URL)
- **Any special configuration** required to reproduce the issue
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible)
- **Impact of the issue**, including how an attacker might exploit the vulnerability
- **Possible fixes or mitigations** you've identified

### Response Timeline

You should receive a response within **72 hours** (3 business days). If for some reason you do not receive a response within this timeframe, please follow up to ensure we received your original message.

Our security team will:

1. **Acknowledge** your report within 72 hours
2. **Investigate** and validate the vulnerability
3. **Provide an estimated timeline** for a fix
4. **Keep you informed** of progress
5. **Credit you** in the security advisory (unless you prefer to remain anonymous)

## Security Update Process

When a security vulnerability is confirmed:

1. A security advisory is created (private)
2. A fix is developed and tested
3. A new version is released with the fix
4. The security advisory is published
5. All users are notified to update

## Security Best Practices

When deploying SecPal:

### On-Premise Deployment

- Keep all dependencies up to date
- Use strong, unique passwords
- Enable HTTPS/TLS for all connections
- Regular security audits and updates
- Implement proper firewall rules
- Regular backups with encryption
- Monitor logs for suspicious activity

### Development

- All commits must be signed
- Code reviews for all changes
- Automated security scanning in CI/CD
- Regular dependency audits
- REUSE compliance for licensing

### Data Protection

- Encrypt sensitive data at rest
- Encrypt all data in transit
- Implement proper access controls
- Regular security training for users
- GDPR compliance for EU users

## Preferred Languages

We prefer all communications to be in:

- 🇬🇧 **English**
- 🇩🇪 **German** (Deutsch)

## Hall of Fame

We recognize and thank the following security researchers for responsibly disclosing vulnerabilities:

<!-- List will be updated as vulnerabilities are reported and fixed -->

_Be the first to help secure SecPal!_

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Security Headers](https://securityheaders.com/)

---

Thank you for helping keep SecPal and its users safe!
