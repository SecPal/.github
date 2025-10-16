<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Cross-Repository Audit Report

**Date:** 2025-10-16
**Auditor:** GitHub Copilot (AI Agent)
**Scope:** SecPal/.github vs SecPal/contracts
**Context:** Post-Phase A Cleanup, Pre-Option B/C Audit

---

## Executive Summary

Comprehensive cross-repository audit revealed **1 critical security issue** (fixed), several opportunities for DRY improvements, and validated successful Phase 1b implementation.

### Critical Findings

1. ✅ **FIXED: Branch Protection Misconfiguration in contracts**
   - **Severity:** Critical
   - **Impact:** Branch protection was not enforcing checks (name mismatch)
   - **Resolution:** Updated all 10 required checks to match actual check names

### Key Findings

2. ✅ **Phase 1b Success:** Copilot Review workflow perfectly synchronized
3. ⚠️ **DRY Opportunities:** 4 workflows not yet using reusables (security, deps, license, commits)
4. ⚠️ **Format/REUSE:** contracts uses separate files, .github uses combined config-checks.yml
5. ✅ **Git Hooks:** Documented as synchronized in README (not verified in this audit)

---

## 1. Branch Protection Analysis

### Issue: Incorrect Check Names in contracts Repository

**Problem Discovery:**

Branch protection in `SecPal/contracts` was configured with old-style check names that no longer matched actual workflow outputs:

```json
// BEFORE (incorrect)
{
  "contexts": [
    "Code Formatting/prettier (pull_request)",
    "Security Scanning/npm-audit (pull_request)",
    "Verify Copilot Review"
  ]
}
```

Actual check names from workflows:

```
prettier
npm-audit
Verify Copilot Review / Verify Copilot Review
```

**Root Cause:**

Check names changed during workflow updates but branch protection was not updated. This is a recurrence of **Lesson #21** (Branch Protection Check Names Must Match Exactly).

**Impact:**

- PRs could merge without required checks passing
- GitHub UI showed checks passing but merge would fail with cryptic errors
- Security workflows (codeql, npm-audit, actions-security) not enforced

**Resolution:**

```bash
# Fixed contracts branch protection
gh api repos/SecPal/contracts/branches/main/protection/required_status_checks \
  -X PATCH --input - << 'EOF'
{
  "strict": true,
  "contexts": [
    "prettier",
    "reuse",
    "contracts-tests",
    "verify-commits",
    "dependency-review",
    "check-npm-licenses",
    "npm-audit",
    "actions-security",
    "codeql",
    "Verify Copilot Review / Verify Copilot Review"
  ]
}
EOF
```

**Current State:**

| Repository  | Required Checks | Status                |
| ----------- | --------------- | --------------------- |
| `.github`   | 8 contexts      | ✅ Correct            |
| `contracts` | 10 contexts     | ✅ Fixed (2025-10-16) |

**Differences Explained:**

- `contracts` has `codeql` and `contracts-tests` (repo-specific)
- `.github` has `Code Formatting` and `REUSE Compliance` (job names differ)

---

## 2. Workflow Synchronization Status

### 2.1 Copilot Review Enforcement ✅

**Status:** PERFECTLY SYNCHRONIZED (Phase 1b Success)

Both repositories use the centralized reusable workflow:

```yaml
# .github/.github/workflows/copilot-review-check.yml
# contracts/.github/workflows/copilot-review-check.yml

jobs:
  verify-copilot-review:
    name: Verify Copilot Review
    uses: SecPal/.github/.github/workflows/reusable-copilot-review.yml@main
    permissions:
      pull-requests: read
      checks: write
```

**Benefits:**

- Single source of truth (180 lines centralized)
- 89% code reduction per repo
- Automatic updates propagate via `@main` reference

### 2.2 Security Scanning

**Status:** ⚠️ NOT USING REUSABLES

| Repository  | Implementation                  |
| ----------- | ------------------------------- |
| `.github`   | Standalone workflow (~60 lines) |
| `contracts` | Standalone workflow (~80 lines) |

**Analysis:**

- Both implement: npm-audit, actions-security, codeql
- Similar but not identical (different triggers, job names)
- **Recommendation:** Create `reusable-security.yml` (Phase 2)

### 2.3 Dependency Review

**Status:** ⚠️ REUSABLE EXISTS BUT NOT USED

**Finding:**

- `.github` has `reusable-dependency-review.yml` (created but unused!)
- Both repos use standalone `dependency-review.yml`

**Investigation:**

```bash
# Check if reusable is called anywhere
grep -r "reusable-dependency-review" .github/workflows/
# Result: No matches
```

**Analysis:**
The reusable was created (per DRY plan) but migration was never completed. This is a **half-finished DRY implementation**.

**Recommendation:**

- Migrate both repos to use the reusable
- Or remove the unused reusable file (technical debt)

### 2.4 License Checking

**Status:** ⚠️ SAME AS DEPENDENCY REVIEW

- `reusable-license-check.yml` exists but is not used
- Both repos have standalone `license-check.yml`
- Same technical debt pattern

### 2.5 Signed Commits Verification

**Status:** ⚠️ NO REUSABLE

- No reusable exists for this
- Both repos have standalone implementations
- Likely similar logic (not verified in detail)

### 2.6 Code Formatting & REUSE Compliance

**Status:** ⚠️ DIFFERENT APPROACHES

| Repository  | Approach                              |
| ----------- | ------------------------------------- |
| `.github`   | `config-checks.yml` (combined)        |
| `contracts` | `format.yml` + `reuse.yml` (separate) |

**Analysis:**

- Both are valid approaches
- Not a DRY violation (different structural choices)
- **Decision:** Accept difference (not worth standardizing)

---

## 3. Reusable Workflows Inventory

### Created Reusables (in .github)

1. ✅ **reusable-copilot-review.yml** - IN USE (both repos)
2. ⚠️ **reusable-dependency-review.yml** - CREATED BUT UNUSED
3. ⚠️ **reusable-license-check.yml** - CREATED BUT UNUSED

### Missing Reusables (opportunities)

4. ❌ **reusable-security.yml** - Should exist for security scanning
5. ❌ **reusable-signed-commits.yml** - Should exist for commit verification

---

## 4. Repository-Specific Workflows

### contracts-only workflows (expected)

- `tests.yml` - Contract tests (repo-specific ✅)
- `format.yml` - Prettier formatting (could use reusable)
- `reuse.yml` - REUSE compliance (could use reusable)

### .github-only workflows (expected)

- `config-checks.yml` - Combined format + REUSE (repo-specific ✅)

---

## 5. Git Hooks Synchronization

**Status:** ✅ DOCUMENTED AS SYNCHRONIZED

Per `.githooks/README.md`:

> **Synchronized with:** the `SecPal/.github` and `SecPal/contracts` repositories

**Files:**

- `.githooks/pre-commit` (identical in both repos, per documentation)
- Installation: `git config core.hooksPath .githooks`

**Not Verified in This Audit:**

- Actual file content comparison (would require cloning contracts locally)
- **Recommendation:** Add to Phase C deep audit

---

## 6. Recommendations

### Immediate Actions (Critical)

1. ✅ **COMPLETED:** Fix contracts branch protection (done 2025-10-16)

### Phase 2 (DRY Completion)

2. **Migrate to existing reusables:**
   - Update `dependency-review.yml` in both repos to call `reusable-dependency-review.yml`
   - Update `license-check.yml` in both repos to call `reusable-license-check.yml`
   - Delete or mark unused reusables as deprecated

3. **Create missing reusables:**
   - `reusable-security.yml` for security scanning
   - `reusable-signed-commits.yml` for commit verification

### Phase 3 (Standardization)

4. **Format/REUSE workflows:**
   - Decide on standard approach (combined vs separate)
   - Document decision in DRY-ANALYSIS-AND-STRATEGY.md
   - Optional: Standardize if valuable

5. **Git hooks verification:**
   - Add automated sync checking
   - Create test to ensure hooks are identical
   - Document sync process

### Continuous Monitoring

6. **Branch protection drift detection:**
   - Create script to compare branch protection across repos
   - Run weekly or on workflow changes
   - Alert on mismatches

7. **Workflow drift detection:**
   - Compare workflow files regularly
   - Ensure reusables are actually used
   - Detect abandoned reusables

---

## 7. Lessons Learned

### New Lesson: Incomplete DRY Implementations

**Problem:** Reusable workflows were created (`reusable-dependency-review.yml`, `reusable-license-check.yml`) but never integrated.

**Root Cause:**

- Phase 1b focused only on Copilot Review
- Other reusables created but migration not completed
- No verification that reusables are actually used

**Prevention:**

- When creating reusables, immediately migrate all callers
- Add grep check: "Is this reusable actually called?"
- Document completion status in DRY strategy

### Lesson #21 Recurrence

**Finding:** Branch protection misconfiguration in contracts (same issue as PR #26/27)

**Root Cause:**

- Workflows updated but branch protection not updated
- Manual sync required (no automation)

**Prevention:**

- Add branch protection update to workflow deployment checklist
- Create script to verify check names match
- Run after every workflow change

---

## 8. Audit Methodology

### Tools Used

- GitHub CLI (`gh api`) for repository introspection
- GraphQL API for detailed queries
- Manual file inspection for workflow analysis

### Scope

- ✅ Branch protection settings
- ✅ Workflow file inventory
- ✅ Reusable workflow usage
- ✅ DRY compliance check
- ⚠️ Git hooks (documented only, not verified)
- ❌ Repository settings (secrets, environments) - deferred
- ❌ Documentation cross-links - deferred

### Limitations

- Did not clone contracts repo locally (API-only analysis)
- Did not verify git hooks byte-for-byte
- Did not audit repository settings beyond branch protection
- Did not verify documentation synchronization

---

## 9. Next Steps

### Immediate (Done)

- ✅ Fix contracts branch protection
- ✅ Document audit findings

### Short-term (This Session)

- [ ] Complete Option C (Deep Audit of all workflows)
- [ ] LESSONS-LEARNED split (2400+ lines → individual files)
- [ ] Document Lesson #23 (after split)

### Medium-term (Phase 2)

- [ ] Migrate dependency-review to reusable
- [ ] Migrate license-check to reusable
- [ ] Create reusable-security.yml
- [ ] Create reusable-signed-commits.yml
- [ ] Implement drift detection

---

## Appendix A: Branch Protection Configurations

### .github Repository

```json
{
  "strict": true,
  "contexts": [
    "Code Formatting",
    "REUSE Compliance",
    "actions-security",
    "check-npm-licenses",
    "dependency-review",
    "npm-audit",
    "verify-commits",
    "Verify Copilot Review / Verify Copilot Review"
  ]
}
```

### contracts Repository

```json
{
  "strict": true,
  "contexts": [
    "prettier",
    "reuse",
    "contracts-tests",
    "verify-commits",
    "dependency-review",
    "check-npm-licenses",
    "npm-audit",
    "actions-security",
    "codeql",
    "Verify Copilot Review / Verify Copilot Review"
  ]
}
```

---

## Appendix B: Workflow File Inventory

### .github/.github/workflows/

- config-checks.yml
- copilot-review-check.yml ✅ (calls reusable)
- dependency-review.yml ⚠️ (should call reusable)
- license-check.yml ⚠️ (should call reusable)
- **reusable-copilot-review.yml** (used)
- **reusable-dependency-review.yml** (unused!)
- **reusable-license-check.yml** (unused!)
- security.yml ⚠️ (should be reusable)
- signed-commits.yml ⚠️ (should be reusable)

### contracts/.github/workflows/

- copilot-review-check.yml ✅ (calls reusable)
- dependency-review.yml ⚠️ (should call reusable)
- format.yml
- license-check.yml ⚠️ (should call reusable)
- reuse.yml
- security.yml ⚠️ (should be reusable)
- signed-commits.yml ⚠️ (should be reusable)
- tests.yml

---

**Document Version:** 1.0
**Status:** COMPLETED
**Follow-up:** Option C (Deep Audit) + LESSONS Split + Lesson #23
