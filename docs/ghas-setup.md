<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# GitHub Advanced Security Baseline for SecPal

Quick-start guide for configuring and auditing the organization-wide GitHub security baseline.

## 🎯 Setup Workflow (when repo exists)

### 1️⃣ **Enable GHAS Features**

```bash
gh api -X PATCH repos/SecPal/{REPO_NAME} \
  -f allow_auto_merge=true \
  -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"},"dependabot_security_updates":{"status":"enabled"}}'
```

### Baseline Settings

Apply these defaults to every SecPal repository unless a documented exception exists:

- `allow_auto_merge=true` so Dependabot auto-merge workflows can actually enable GitHub auto-merge
- `secret_scanning=enabled`
- `secret_scanning_push_protection=enabled`
- `dependabot_security_updates=enabled`
- label baseline synced from [docs/labels.md](./labels.md), including `github-actions`
- ensure an active `Copilot review for default branch` ruleset exists on the default branch for each repository

The following features are currently reviewed separately and are not part of the required baseline for every repository:

- `secret_scanning_non_provider_patterns`
- `secret_scanning_validity_checks`

### 2️⃣ **Generate CodeQL Workflow**

```bash
# GitHub auto-generates appropriate CodeQL config:
gh workflow init codeql -R SecPal/{REPO_NAME}

# Or manually: https://github.com/SecPal/{REPO_NAME}/security/code-scanning
```

### 3️⃣ **Configure Dependabot**

See [Dependabot Template](#-dependabot-template) below.

## Repository Classes

### **React Frontend / Tooling Repositories**

- **Examples**: `frontend`, `android`, `.github`, `secpal.app`
- **Stack**: React, TypeScript, Astro, shell, workflows
- **CodeQL**: `javascript-typescript`
- **Extras**: npm audit, ESLint Security Plugin

### **Laravel Backend**

- **Example**: `api`
- **Stack**: Laravel, PHP 8.4, PostgreSQL
- **CodeQL**: ⚠️ **NOT SUPPORTED** - PHP is not supported by CodeQL
- **Alternatives**: Use PHPStan (level: max), Psalm, or Semgrep for static analysis
- **Extras**: Composer audit, Laravel Pint (code style)

### **OpenAPI Contracts Repository**

- **Example**: `contracts`
- **Stack**: OpenAPI 3.1, Node.js tooling
- **CodeQL**: Optional, depending on whether repository-owned code justifies code scanning
- **Extras**: OpenAPI spec validation, dependency review, and workflow hardening

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

### Copilot Review Ruleset

Standardize the `Copilot review for default branch` ruleset across repositories so the same review gate applies to each default branch.

Or manually: **Settings → Rules → Rulesets**

## 📊 Security Dashboard

After activation:

- **Repository**: `https://github.com/SecPal/{REPO}/security`
- **Organization**: `https://github.com/organizations/SecPal/security/overview`

### Available Tabs

- **Code scanning** - CodeQL Findings
- **Secret scanning** - Leaked Credentials
- **Dependabot** - Vulnerable Dependencies
- **Advisories** - CVE Database

## Audit Commands

Use these checks to confirm the live baseline instead of relying on stale snapshots:

```bash
gh api repos/SecPal/{REPO_NAME} --jq '{
  allow_auto_merge,
  secret_scanning: .security_and_analysis.secret_scanning.status,
  push_protection: .security_and_analysis.secret_scanning_push_protection.status,
  dependabot_security_updates: .security_and_analysis.dependabot_security_updates.status,
  non_provider_patterns: .security_and_analysis.secret_scanning_non_provider_patterns.status,
  validity_checks: .security_and_analysis.secret_scanning_validity_checks.status
}'

gh api repos/SecPal/{REPO_NAME}/rulesets --jq '.[] | [.name, .enforcement] | @tsv'
gh label list -R SecPal/{REPO_NAME} --limit 200
```

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

**Status**: ✅ Active baseline for live repositories
**Maintained by**: SecPal Security Team
**Last Updated**: March 2026
