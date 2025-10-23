# GitHub Advanced Security Setup for SecPal

Quick-start guide for enabling GHAS in new repositories.

## 🎯 Setup Workflow (when repo exists)

### 1️⃣ **Enable GHAS Features**

```bash
gh api -X PATCH repos/SecPal/{REPO_NAME} \
  -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'
```

### 2️⃣ **Generate CodeQL Workflow**

```bash
# GitHub auto-generates appropriate CodeQL config:
gh workflow init codeql -R SecPal/{REPO_NAME}

# Or manually: https://github.com/SecPal/{REPO_NAME}/security/code-scanning
```

### 3️⃣ **Configure Dependabot**

See [Dependabot Template](#-dependabot-template) below.

## 📋 Planned Repositories

### **React Frontend** (not yet created)

- **Stack**: React, TypeScript
- **CodeQL**: `javascript-typescript`
- **Extras**: npm audit, ESLint Security Plugin

### **Laravel Backend** (not yet created)

- **Stack**: Laravel, PHP 8.4, PostgreSQL
- **CodeQL**: ⚠️ **NOT SUPPORTED** - PHP is not supported by CodeQL
- **Alternatives**: Use PHPStan (level: max), Psalm, or Semgrep for static analysis
- **Extras**: Composer audit, Laravel Pint (code style)

### **OpenAPI Service** (not yet created)

- **Stack**: TBD (Node.js/Python/Go)
- **CodeQL**: Language-dependent
- **Extras**: OpenAPI Spec Validation (Spectral OWASP)

## 🔒 What CodeQL Detects (Language-specific)

<details>
<summary><strong>JavaScript/TypeScript</strong> (React, OpenAPI if Node.js)</summary>

- XSS, Code Injection, Prototype Pollution
- SQL/NoSQL Injection, Command Injection
- Path Traversal, Hardcoded Credentials
- Insecure Randomness, Weak Cryptography

</details>

<details>
<summary><strong>PHP</strong> (Laravel)</summary>

- SQL Injection, XSS, CSRF
- Command Injection, Path Traversal
- Insecure Deserialization, Mass Assignment
- Hardcoded Credentials, Weak Cryptography

</details>

<details>
<summary><strong>Python</strong> (if OpenAPI in Python)</summary>

- SQL Injection, Command Injection
- Path Traversal, SSRF
- Deserialization, XXE

</details>

<details>
<summary><strong>Go</strong> (if OpenAPI in Go)</summary>

- SQL Injection, Command Injection
- Path Traversal, Resource Leaks
- Race Conditions, Insecure TLS

</details>

## 📝 Dependabot Template

Create `.github/dependabot.yml` in each repository:

```yaml
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: AGPL-3.0-or-later

version: 2
updates:
  # Package Manager (npm/composer/pip/gomod)
  - package-ecosystem: "npm" # or: composer, pip, gomod
    directory: "/"
    schedule:
      interval: "daily"
      time: "04:00"
      timezone: "Europe/Berlin"
    labels:
      - "dependencies"
      - "dependabot"
    open-pull-requests-limit: 10

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "daily"
      time: "04:00"
      timezone: "Europe/Berlin"
    labels:
      - "dependencies"
      - "github-actions"
```

## 🎯 Branch Protection (recommended)

For `main` branch in each repository:

```bash
# Via GitHub CLI:
gh api repos/SecPal/{REPO_NAME}/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["CodeQL"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":0}' \
  --field restrictions=null
```

**Note:**

- `enforce_admins=true`: Non-negotiable - even admins must follow rules
- `required_approving_review_count=0`: Single maintainer project, automated checks provide quality gates
- Required status checks: Adjust based on repository type (CodeQL for JS/TS only, not for PHP)

Or manually: **Settings → Branches → Add rule**

## 📊 Security Dashboard

After activation:

- **Repository**: `https://github.com/SecPal/{REPO}/security`
- **Organization**: `https://github.com/organizations/SecPal/security/overview`

### Available Tabs

- **Code scanning** - CodeQL Findings
- **Secret scanning** - Leaked Credentials
- **Dependabot** - Vulnerable Dependencies
- **Advisories** - CVE Database

## 🚀 Setup for New Repositories

### When repository is created

#### 1. Enable GHAS

```bash
gh api -X PATCH repos/SecPal/{REPO_NAME} \
  -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'
```

#### 2. CodeQL Workflow

GitHub can automatically generate the appropriate config:

- Go to **Security → Code scanning → Set up → Advanced**
- GitHub detects the language and creates `.github/workflows/codeql.yml`
- Or use the pre-made templates from `.github/workflow-templates/`

#### 3. Dependabot

Copy the [template above](#-dependabot-template) to `.github/dependabot.yml`

#### 4. Branch Protection

See [Branch Protection section](#-branch-protection-recommended)

## 🎯 Best Practices

- ✅ **Review findings weekly** - Schedule security review meetings
- ✅ **Mark false positives** - "Used in tests" / "False positive"
- ✅ **Enable auto-fix** - Dependabot auto-merge for patches
- ✅ **Use GitHub Secrets** - Never commit credentials to code
- ✅ **Enforce branch protection** - CodeQL must pass before merge

## 📚 References

- **GHAS Docs**: <https://docs.github.com/en/code-security>
- **CodeQL Queries**: <https://codeql.github.com/codeql-query-help/>
- **Dependabot**: <https://docs.github.com/en/code-security/dependabot>
- **Security Lab**: <https://github.com/github/securitylab>

---

**Status**: ✅ Ready for rollout when repositories are created
**Maintained by**: SecPal Security Team
**Last Updated**: October 2025
