<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Security Policy

## Supported Versions

We follow [Semantic Versioning](https://semver.org/) (SEMVER). Security updates are provided for the following versions:

| Version | Supported | Notes                                                     |
| ------- | --------- | --------------------------------------------------------- |
| 0.x.x   | ✅        | Development phase - all versions receive security updates |
| < 0.0.1 | ❌        | Not yet released                                          |

**Note:** Once we reach 1.0.0 (stable release), we will support:

- The latest major version (e.g., 2.x.x)
- The previous major version for 6 months after new major release
- Critical security patches may be backported to older versions on a case-by-case basis

## Reporting a Vulnerability

**🔒 DO NOT open public issues for security vulnerabilities!**

We take security seriously. If you discover a security vulnerability, please report it responsibly:

### 1. GitHub Security Advisories (Preferred)

1. Go to the repository's **Security** tab
2. Click **"Report a vulnerability"**
3. Fill out the advisory form with:
   - Vulnerability description
   - Affected versions
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

**Benefits:**

- Private communication channel
- Coordinated disclosure timeline
- CVE assignment (if applicable)
- Credit in security advisory

### 2. Email Contact

If you cannot use GitHub Security Advisories, contact us at:

**🔐 <security@secpal.app>** (PGP key available on request)

**Please include:**

- Brief description of the vulnerability
- Steps to reproduce
- Affected components/versions
- Your contact information (for follow-up)

## Response Timeline

We are committed to responding quickly to security reports:

| Severity | Initial Response | Fix Target | Disclosure |
| -------- | ---------------- | ---------- | ---------- |
| Critical | 24 hours         | 7 days     | After fix  |
| High     | 48 hours         | 14 days    | After fix  |
| Medium   | 72 hours         | 30 days    | After fix  |
| Low      | 7 days           | 60 days    | After fix  |

**Severity Definitions:**

- **Critical:** Remote code execution, authentication bypass, SQL injection
- **High:** Privilege escalation, unauthorized data access, XSS with sensitive data exposure
- **Medium:** Information disclosure, CSRF, moderate data leaks
- **Low:** Minor information leaks, low-impact bugs

## Security Update Process

When a vulnerability is confirmed:

1. **Acknowledgment:** We confirm receipt and severity assessment
2. **Investigation:** We reproduce and analyze the vulnerability
3. **Fix Development:** We develop and test a patch
4. **Coordinated Disclosure:**
   - Security advisory created (private)
   - Fix released as patch version (e.g., 0.3.1 → 0.3.2)
   - Security advisory published (public)
   - CVE assigned (if applicable)
5. **Communication:**
   - GitHub Security Advisory
   - Release notes
   - Dependabot alerts (for downstream users)

## Security Best Practices for Contributors

When contributing to SecPal, follow these security guidelines:

### Code Review Checklist

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] Input validation on all user inputs
- [ ] SQL queries use parameterized statements (no string concatenation)
- [ ] Authentication/Authorization checks in place
- [ ] Sensitive data encrypted at rest and in transit
- [ ] Error messages don't leak sensitive information
- [ ] Dependencies scanned for known vulnerabilities
- [ ] HTTPS/TLS enforced for all network communication

### Pre-Commit Security Checks

All PRs automatically run:

- **Secret Scanning:** GitHub Secret Scanning with push protection
- **Dependency Scanning:** Dependabot security updates
- **SAST:** CodeQL (JavaScript/TypeScript only)
- **PHP Security:** PHPStan (level: max), Laravel Pint
- **Linting:** ESLint security rules

### Secure Development Guidelines

1. **Never commit secrets:**
   - Use environment variables (`.env`)
   - Utilize secret management services
   - Enable push protection (automatically enabled)

2. **Keep dependencies updated:**
   - Dependabot creates PRs daily (04:00 CET)
   - Security updates have priority
   - Review and merge promptly

3. **Follow OWASP Top 10:**
   - [OWASP Top Ten](https://owasp.org/www-project-top-ten/)
   - Regular security training encouraged

4. **Validate all inputs:**
   - Server-side validation (never trust client)
   - Sanitize outputs to prevent XSS
   - Use framework's built-in protection (Laravel, React)

5. **Least Privilege Principle:**
   - Minimal permissions for services
   - Role-based access control (RBAC)
   - Regular permission audits

## Security Features

SecPal repositories have the following security features enabled:

| Feature                         | Status | Description                            |
| ------------------------------- | ------ | -------------------------------------- |
| **Secret Scanning**             | ✅     | Detects leaked credentials             |
| **Push Protection**             | ✅     | Blocks commits with secrets            |
| **Dependabot Security Updates** | ✅     | Automated security patches             |
| **Dependabot Version Updates**  | ✅     | Daily dependency updates (04:00 CET)   |
| **CodeQL Analysis**             | ✅     | SAST for JavaScript/TypeScript         |
| **Branch Protection**           | ✅     | Enforced status checks, signed commits |
| **Security Advisories**         | ✅     | Private vulnerability reporting        |
| **Two-Factor Authentication**   | ✅     | Required for all maintainers           |

## Known Security Limitations

### CodeQL Language Support

**⚠️ PHP is NOT supported by GitHub CodeQL.**

We compensate with:

- **PHPStan** (level: max) - Static analysis
- **Laravel Pint** - Code style enforcement
- **Manual security reviews** for PHP code
- **Consider:** Psalm, Semgrep for additional PHP security scanning

### API Rate Limiting

- Currently: No rate limiting implemented
- **Planned:** Rate limiting for public APIs (v0.5.0)
- **Mitigation:** Monitor for unusual traffic patterns

### CORS Configuration

- Currently: Permissive CORS for development
- **Planned:** Strict CORS policy for production (v0.3.0)

## Security Roadmap

Planned security enhancements:

- [ ] **v0.3.0:** Production-ready CORS configuration
- [ ] **v0.5.0:** API rate limiting
- [ ] **v0.7.0:** Comprehensive audit logging
- [ ] **v0.9.0:** Penetration testing
- [ ] **v1.0.0:** Security certification (OWASP ASVS Level 2)

## Hall of Fame

We appreciate responsible disclosure! Security researchers who report valid vulnerabilities will be credited here (with permission):

<!-- This section will be updated as vulnerabilities are reported and fixed -->

_No vulnerabilities reported yet._

---

## Additional Resources

- [OWASP Top Ten](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)
- [Laravel Security Documentation](https://laravel.com/docs/security)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)

## Contact

- **Security Issues:** Use GitHub Security Advisories or <security@secpal.app>
- **General Questions:** Open a Discussion in the repository
- **Non-Security Bugs:** Open an Issue using our bug report template

**Last Updated:** 2025-10-25
