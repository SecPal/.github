<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Prevention Strategy Automation

**Purpose:** Automated validation of prevention measures to ensure quality controls remain active  
**Created:** 2025-10-18  
**Scope:** All SecPal repositories

---

## Overview

This document describes the automated validation system that ensures prevention measures from the post-audit action items remain properly configured across all repositories.

**Why automate?**
- Settings can drift over time
- New repositories need validation
- Manual checks are error-prone
- Early detection prevents quality regressions

---

## Components

### 1. Validation Script (Manual + Automated)

**File:** `scripts/validate-prevention-strategy.sh`

**Usage:**
```bash
# Validate a single repository
./scripts/validate-prevention-strategy.sh SecPal/.github

# Validate contracts repository
./scripts/validate-prevention-strategy.sh SecPal/contracts
```

**What it checks:**
1. ✅ Branch protection - `enforce_admins: true`
2. ✅ Required status checks configured
3. ✅ Copilot Review in required checks (Lesson #18)
4. ✅ Workflows running successfully
5. ✅ Status check names match job names (Lesson #1, #21)
6. ✅ Reusable workflows in use (DRY)

**Exit codes:**
- `0` - All checks passed
- `1` - One or more checks failed

---

### 2. GitHub Actions Workflow (Automated)

**File:** `.github/workflows/prevention-strategy-validation.yml`

**Schedule:** Monthly (1st of each month at 09:00 UTC)

**Manual trigger:** Available via `workflow_dispatch`

**What it does:**
```
1. Runs validation script for each repository
2. Uploads validation reports as artifacts
3. Fails workflow if any repo fails validation
4. Provides summary of results
```

**Repositories validated:**
- `SecPal/.github`
- `SecPal/contracts`
- (+ additional repos via manual trigger input)

**Artifacts:** Validation reports retained for 90 days

---

## Usage Scenarios

### Scenario 1: Monthly Automated Check

**Trigger:** Automatic (1st of month)

**Process:**
```
1. Workflow runs automatically
2. Validates all repositories
3. If failures:
   - Workflow fails
   - Artifacts show which checks failed
   - Team investigates and remediates
4. If success:
   - Workflow succeeds
   - All prevention measures confirmed active
```

### Scenario 2: New Repository Setup

**Trigger:** Manual (`workflow_dispatch`)

**Process:**
```bash
# 1. Go to GitHub Actions UI
# 2. Select "Prevention Strategy Validation" workflow
# 3. Click "Run workflow"
# 4. Enter additional repos: "SecPal/new-repo"
# 5. Run
# 6. Check results - fix any failures
```

### Scenario 3: Post-Configuration Change

**When to run:**
- After modifying branch protection
- After adding/removing required checks
- After updating workflows
- After any security setting changes

**Process:**
```bash
# Local validation before committing
./scripts/validate-prevention-strategy.sh SecPal/.github

# Or trigger GitHub Actions manually
# (via workflow_dispatch)
```

### Scenario 4: Audit Preparation

**Before quarterly/annual audits:**
```
1. Trigger manual validation for ALL repos
2. Review validation reports
3. Fix any failures
4. Document results in audit report
```

---

## Validation Checklist

### Per Repository

| Check | Expected | Lesson Reference |
|-------|----------|------------------|
| `enforce_admins` | `true` | #6, #13 |
| Required status checks exist | Yes | #1, #21 |
| Copilot Review required | Yes | #18 |
| Status check names match jobs | Yes | #1, #21 |
| Workflows running | Success | General |
| Reusable workflows used | Yes | DRY |

### Cross-Repository

- All repos have consistent settings
- No drift between repositories
- New repos follow setup guide

---

## Remediation

**If validation fails:**

1. **Check artifact for details:**
   - Download validation report
   - Identify which check failed
   - Note the specific repository

2. **Fix the issue:**
   - **Branch protection:** Update via GitHub UI or API
   - **Required checks:** Add missing check to branch protection
   - **Workflows:** Fix workflow files, re-enable if disabled
   - **Status check names:** Align with job names (Lesson #1, #21)

3. **Reference documentation:**
   - `docs/PREVENTION-STRATEGY-VALIDATION-2025-10-18.md` - Initial validation findings
   - `docs/REPOSITORY-SETUP-GUIDE.md` - Setup checklist
   - `docs/lessons/` - Specific lesson references

4. **Re-validate:**
   ```bash
   # Local
   ./scripts/validate-prevention-strategy.sh SecPal/repo-name
   
   # Or trigger GitHub Actions manually
   ```

5. **Document fix:**
   - If systematic issue: Create lesson
   - If one-time: Note in validation report
   - Update setup guide if needed

---

## Maintenance

### Adding New Repositories

**Update workflow matrix:**
```yaml
# .github/workflows/prevention-strategy-validation.yml
matrix:
  repo:
    - 'SecPal/.github'
    - 'SecPal/contracts'
    - 'SecPal/new-repo'  # Add here
```

### Modifying Validation Logic

**Update script:**
```bash
# scripts/validate-prevention-strategy.sh
# Add new checks in numbered sections
# Maintain exit code logic (0 = pass, 1 = fail)
```

### Changing Schedule

```yaml
# .github/workflows/prevention-strategy-validation.yml
on:
  schedule:
    - cron: '0 9 1 * *'  # Modify cron expression
```

**Current:** Monthly (1st at 09:00 UTC)  
**Alternatives:**
- Weekly: `'0 9 * * 1'` (every Monday)
- Quarterly: `'0 9 1 1,4,7,10 *'` (Jan, Apr, Jul, Oct)

---

## Examples

### Example 1: Manual Validation

```bash
$ ./scripts/validate-prevention-strategy.sh SecPal/.github

🔍 Prevention Strategy Validation for SecPal/.github
================================================

📋 Check 1: Pre-commit Hooks
⚠️  Cannot verify remotely - manual check required

📋 Check 2: Branch Protection - enforce_admins
✅ enforce_admins: true

📋 Check 3: Required Status Checks
✅ Required status checks configured:
   - Code Formatting
   - REUSE Compliance
   - Verify Copilot Review / Verify Copilot Review
   ...

📋 Check 4: Copilot Review Enforcement
✅ Copilot Review is required:
   - Verify Copilot Review / Verify Copilot Review

================================================
📊 Validation Summary
================================================
✅ All checks passed!
```

### Example 2: Validation Failure

```bash
$ ./scripts/validate-prevention-strategy.sh SecPal/new-repo

...

📋 Check 4: Copilot Review Enforcement
❌ Copilot Review NOT in required checks (Lesson #18)

================================================
📊 Validation Summary
================================================
❌ 1 check(s) failed

🔧 Remediation:
   See: docs/PREVENTION-STRATEGY-VALIDATION-2025-10-18.md
   See: docs/REPOSITORY-SETUP-GUIDE.md
```

---

## Integration with Existing Processes

### Repository Setup

**When creating new repository:**
```
1. Follow REPOSITORY-SETUP-GUIDE.md
2. Run validation script
3. Fix any failures
4. Add repo to automation workflow matrix
5. Verify monthly automation includes new repo
```

### Pull Request Process

**Not run on every PR** (too heavy)  
**When to validate:**
- Workflow files changed
- Branch protection settings changed
- After remediation PRs

### Quarterly Audit

**Include in audit process:**
1. Review last 3 months of validation runs
2. Document any failures and fixes
3. Update lessons if new patterns emerge
4. Verify all repos in scope

---

## Related Documentation

- **ACTION-ITEMS.md:** Step 2 - Prevention Strategy validation
- **PREVENTION-STRATEGY-VALIDATION-2025-10-18.md:** Initial validation findings
- **REPOSITORY-SETUP-GUIDE.md:** New repository setup checklist
- **Lesson #1:** Status check context names
- **Lesson #6:** Admin bypass disabled
- **Lesson #13:** Never use `--admin` flag
- **Lesson #17:** Pre-commit hook installation
- **Lesson #18:** Copilot Review Enforcement
- **Lesson #21:** Status check name recurrence

---

**Last Updated:** 2025-10-18  
**Automation Status:** Active (monthly schedule)  
**Next Scheduled Run:** 2025-11-01 09:00 UTC
