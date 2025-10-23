# GitHub Advanced Security Setup for SecPal

Quick-start guide for enabling GHAS in new repositories.

## 🔓 Free Plan vs GitHub Advanced Security

SecPal currently operates on GitHub's **Free plan**. This affects which security features are available:

### ✅ Available on Free Plan (Public Repos)

- **Secret Scanning** - Detects secrets from known providers (GitHub, AWS, Azure, etc.)
- **Push Protection** - Blocks commits containing detected secrets
- **Dependabot Alerts** - Vulnerability alerts for dependencies
- **Dependabot Security Updates** - Automated PRs to fix vulnerabilities
- **Manual Code Scanning** - Self-hosted CodeQL analysis

### ❌ Requires GitHub Advanced Security (GHAS)

**Not available on Free plan - requires GitHub Enterprise Cloud or GHAS add-on:**

- **Non-Provider Pattern Detection** - Generic secret patterns (private keys, custom API tokens)
  - Status: `secret_scanning_non_provider_patterns: disabled`
  - Detects secrets not tied to known service providers
- **Validity Checks** - Verifies if detected secrets are active/valid
  - Status: `secret_scanning_validity_checks: disabled`
  - Sends secret hashes to providers for validation
- **Private Repository Code Scanning** - Automated CodeQL in private repos
- **Secret Scanning in Private Repos** - Full secret scanning for private repositories

### 💡 Workarounds for Free Plan

If GHAS features are needed but not available:

1. **TruffleHog** - Open-source secret scanning with custom patterns
2. **GitGuardian** - Commercial secret scanning (free tier available)
3. **Gitleaks** - Open-source SAST tool for secrets
4. **Manual CodeQL** - Run CodeQL locally or via self-hosted runners

### 📊 Current Organization Status

```json
{
  "plan": "free",
  "advanced_security_enabled_for_new_repositories": false
}
```

**To upgrade:** Contact GitHub Sales or upgrade to GitHub Enterprise Cloud.

## 🎯 Setup Workflow (when repo exists)

### 1️⃣ **Enable Secret Scanning (Free Tier)**

For **public repositories** on Free plan:

```bash
# Enable basic secret scanning + push protection
gh api -X PATCH repos/SecPal/{REPO_NAME} \
  -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'
```

**Note:** Advanced features require GHAS subscription:

```bash
# ❌ NOT available on Free plan - requires GHAS:
# secret_scanning_non_provider_patterns
# secret_scanning_validity_checks
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
- **CodeQL**: `php`
- **Extras**: Composer audit, Psalm/PHPStan

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
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field restrictions=null
```

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

## 🔧 Troubleshooting

### "Feature requires GitHub Advanced Security"

**Problem:** Attempting to enable advanced secret scanning features fails with error:

```json
{
  "message": "Advanced Security must be enabled for this repository",
  "documentation_url": "https://docs.github.com/rest/repos/repos#update-a-repository"
}
```

**Cause:** Free plan does not include:

- `secret_scanning_non_provider_patterns`
- `secret_scanning_validity_checks`
- Private repository code scanning

**Solution:**

1. **Verify organization plan:**

   ```bash
   gh api /orgs/SecPal | jq '.plan.name'
   # Expected: "free"
   ```

2. **Use free tier alternatives:**
   - Keep existing secret scanning enabled (provider patterns work on Free plan)
   - Use open-source tools (TruffleHog, Gitleaks) for custom patterns
   - Consider GitHub Enterprise Cloud if budget allows

3. **Document limitation:**
   - Mark issues as "requires: GitHub Advanced Security"
   - Close as "won't do" until plan upgrade

### CodeQL Not Running Automatically

**Problem:** CodeQL analysis not executing on pull requests.

**Cause:** Automatic CodeQL requires GHAS for private repos.

**Solution:**

- **Public repos:** CodeQL works on Free plan
- **Private repos:** Manual workflow setup required (see [CodeQL section](#2️⃣-generate-codeql-workflow))
- Or upgrade to GHAS for automated analysis

### Secret Scanning Not Detecting Custom Patterns

**Problem:** Generic secrets (private keys, custom tokens) not detected.

**Cause:** Non-provider pattern detection requires GHAS.

**Solution:**

- Use alternative tools:
  - **pre-commit hook:** Add `detect-private-key` hook
  - **TruffleHog:** `trufflehog git file://. --only-verified`
  - **Gitleaks:** `gitleaks detect --source .`

Example pre-commit configuration:

```yaml
# Add to .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: detect-private-key
      - id: check-added-large-files
```

## 📚 References

### GitHub Documentation

- **GHAS Docs**: <https://docs.github.com/en/code-security>
- **CodeQL Queries**: <https://codeql.github.com/codeql-query-help/>
- **Dependabot**: <https://docs.github.com/en/code-security/dependabot>
- **Security Lab**: <https://github.com/github/securitylab>
- **Secret Scanning**: <https://docs.github.com/en/code-security/secret-scanning>

### Alternative Tools (Free/Open Source)

- **TruffleHog**: <https://github.com/trufflesecurity/trufflehog>
- **Gitleaks**: <https://github.com/gitleaks/gitleaks>
- **GitGuardian**: <https://www.gitguardian.com/> (free tier available)
- **pre-commit hooks**: <https://pre-commit.com/>
- **Semgrep**: <https://semgrep.dev/> (SAST alternative to CodeQL)

---

**Status**: ✅ Ready for rollout when repositories are created
**Maintained by**: SecPal Security Team
**Last Updated**: October 2025
