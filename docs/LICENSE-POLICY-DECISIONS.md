<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# License Policy Decisions

**Date:** 2025-10-18
**Status:** Active
**Related:** [AUDIT-REPORT-2025-10-12.md](AUDIT-REPORT-2025-10-12.md), [ACTION-ITEMS.md](ACTION-ITEMS.md)

---

## Executive Summary

This document records all license policy decisions for SecPal repositories, explaining the rationale behind differences and standardization choices.

**Key Decisions:**

- ✅ Repository-specific allowed licenses are **intentional**
- ✅ SSPL-1.0 remains **not explicitly denied** (monitored)
- ✅ Node.js Action standardization: **v6** (latest stable)

---

## 1. Allowed License Differences

### Current State

**`.github` Repository:**

```json
"allowedLicenses": [
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
  "ISC", "0BSD", "CC0-1.0", "Unlicense",
  "WTFPL", "Python-2.0", "AGPL-3.0-or-later"
]
```

**`contracts` Repository:**

```json
"allowedLicenses": [
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
  "ISC", "0BSD", "CC0-1.0", "Unlicense",
  "GPL-3.0-or-later", "LGPL-3.0-or-later",
  "AGPL-3.0", "AGPL-3.0-or-later"
]
```

### Decision: **INTENTIONAL DIFFERENCES** ✅

**Rationale:**

1. **`.github` Unique Licenses:**
   - `WTFPL`: Allows GitHub-specific tooling/scripts with maximum freedom
   - `Python-2.0`: Historical Python tools for CI/CD automation

2. **`contracts` Unique Licenses:**
   - `GPL-3.0-or-later`: Allows copyleft dependencies for type definitions
   - `LGPL-3.0-or-later`: Library-focused copyleft (e.g., for OpenAPI tooling)
   - `AGPL-3.0`: Exact version match (in addition to `-or-later`)

3. **Why Not Unified?**
   - Different dependency ecosystems (CI tools vs. TypeScript libraries)
   - Repository-specific risk profiles
   - Type definitions vs. runtime dependencies

### Action Items

- [x] Document rationale in this file
- [ ] Add policy validation tests (Phase 1 Prevention Strategy)
- [ ] Review annually or when adding new dependencies

---

## 2. SSPL-1.0 License

### Context

SSPL-1.0 (Server Side Public License) was found hardcoded in `.github/dependency-review.yml` during the 2025-10-12 audit but was **not** present in any `.license-policy.json` file.

### Decision: **NOT EXPLICITLY DENIED** ⚠️

**Rationale:**

1. **Current State:**
   - No npm dependencies in SecPal use SSPL-1.0
   - Primarily used by MongoDB and some server software
   - Not relevant for current JavaScript/TypeScript dependencies

2. **Risk Assessment:**
   - **Low immediate risk:** npm ecosystem rarely uses SSPL-1.0
   - **Controversial license:** FSF doesn't consider it "free software"
   - **Copyleft stronger than AGPL:** Would require our entire platform to be open-sourced if used in cloud deployment

3. **Monitoring Strategy:**
   - GitHub Dependency Review will flag SSPL-1.0 if it appears
   - Can be added to `deniedLicenses` immediately if needed
   - Annual review of this decision

### Action Items

- [x] Document decision and rationale
- [ ] Add SSPL-1.0 monitoring to quarterly audit checklist
- [ ] Evaluate adding to `deniedLicenses` if any dependency attempts to use it

### Future Consideration

**Add to `deniedLicenses` if:**

- Any npm package introduces SSPL-1.0
- SecPal plans cloud/SaaS deployment (strong copyleft implications)
- Legal team recommends explicit denial

---

## 3. Node.js Action Version Standardization

### Context

During the 2025-10-12 audit, version inconsistencies were discovered:

- `.github`: Mix of v4, v5
- `contracts`: v6 (latest)

### Decision: **STANDARDIZE ON v6** ✅

**Rationale:**

1. **Version Stability:**
   - v6 is the latest stable release
   - `contracts` has been using v6 without issues
   - Dependabot keeps us up-to-date automatically

2. **Benefits of v6:**
   - Improved caching performance
   - Better Node.js version resolution
   - Security updates and bug fixes

3. **Migration Path:**
   - Low risk: GitHub Actions maintains backward compatibility
   - Can be done incrementally
   - No breaking changes expected

### Current Status (2025-10-18)

**`.github` Repository:**

- All workflows: v6 ✅
- Status: **COMPLETE** (upgraded in this PR)

**`contracts` Repository:**

- All workflows: v6 ✅
- Status: **COMPLETE**

### Action Items

- [x] Upgrade remaining v4 instances in `.github` to v6
  - ✅ `/.github/workflows/config-checks.yml` (completed in this PR)
  - ✅ `/.github/workflows/security.yml` (completed in this PR)
- [ ] Update documentation templates to reference v6
- [ ] Add version check to config-enforcement workflow (future)

### Migration Command

```bash
# Upgrade all setup-node actions to v6 (specific to actions/setup-node)
find .github/workflows -name "*.yml" -type f -exec sed -i 's/actions\/setup-node@v[4-5]/actions\/setup-node@v6/g' {} \;
```

---

## 4. Denied Licenses

### Unified Denied List

Both repositories share the same denied licenses:

```json
"deniedLicenses": ["GPL-2.0", "LGPL-2.0", "LGPL-2.1", "AGPL-1.0"]
```

### Decision: **MAINTAIN UNIFIED DENIED LIST** ✅

**Rationale:**

1. **GPL-2.0, LGPL-2.0, LGPL-2.1:**
   - Incompatible with AGPL-3.0-or-later
   - Cannot be automatically upgraded
   - Strong copyleft with AGPL-incompatible terms

2. **AGPL-1.0:**
   - Explicitly denied despite allowing AGPL-3.0-or-later
   - Version-specific incompatibility
   - Must use AGPL-3.0-or-later or more permissive

3. **Why Unified?**
   - Core legal compatibility applies to entire project
   - Simplifies maintenance
   - Reduces policy drift risk

### Action Items

- [x] Verify both repositories have identical `deniedLicenses`
- [ ] Add test to ensure denied lists stay synchronized
- [ ] Document upgrade path for any denied license that appears

---

## 5. Policy Synchronization Strategy

### Current Approach: **MANUAL WITH AUTOMATION**

**How Policies Are Maintained:**

1. **Source of Truth:** Individual `.license-policy.json` files per repo
2. **Validation:** GitHub Dependency Review workflow (reusable)
3. **Monitoring:** Quarterly audits + Dependabot alerts
4. **Synchronization:** Template-based with manual review

### Future Enhancements (Phase 3)

- [ ] Centralized policy with repo-specific overrides
- [ ] Automated policy validation in CI
- [ ] License policy diff detection in drift workflow
- [ ] Annual policy review reminder

---

## 6. Review Schedule

### Quarterly Review Checklist

- [ ] Check for new licenses in dependencies
- [ ] Verify no denied licenses have been introduced
- [ ] Review SSPL-1.0 monitoring status
- [ ] Confirm Node.js action versions are current
- [ ] Update this document with any changes

### Annual Deep Review

- [ ] Reassess allowed license list
- [ ] Legal team consultation (if available)
- [ ] Industry best practices review
- [ ] AGPL compatibility verification

**Next Quarterly Review:** 2026-01-18
**Next Annual Review:** 2026-10-18

---

## 7. Decision Log

| Date       | Decision                                 | Status | Reviewer |
| ---------- | ---------------------------------------- | ------ | -------- |
| 2025-10-18 | Repository-specific allowed licenses     | Active | Copilot  |
| 2025-10-18 | SSPL-1.0 not explicitly denied (monitor) | Active | Copilot  |
| 2025-10-18 | Standardize on setup-node@v6             | Active | Copilot  |
| 2025-10-18 | Unified denied list maintained           | Active | Copilot  |

---

## 8. References

- [SPDX License List](https://spdx.org/licenses/)
- [AGPL-3.0 Compatibility Guide](https://www.gnu.org/licenses/gpl-faq.html#AllCompatibility)
- [GitHub Dependency Review Documentation](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review)
- [Node.js Action Changelog](https://github.com/actions/setup-node/releases)

---

**Document Owner:** SecPal Maintainers
**Last Updated:** 2025-10-18
**Version:** 1.0
**Status:** ✅ Active
