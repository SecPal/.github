<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lessons Learned Index

**Repository:** SecPal Organization
**Purpose:** Centralized knowledge base from all SecPal repository setups

This directory contains individual lessons learned during the setup and maintenance of SecPal repositories. Each lesson is a self-contained document with problem description, solution, and implementation guidelines.

## 🚦 Start Here

**New AI assistants:** Read [Lesson #0](lesson-00.md) FIRST before making any changes!

## 📚 Lesson Categories

### 🔴 Critical Issues (Lessons #0-10)

Must be addressed immediately in all repositories. These issues can block PRs or compromise security.

| #                   | Lesson                                                             | Status    | Priority |
| ------------------- | ------------------------------------------------------------------ | --------- | -------- |
| [#0](lesson-00.md)  | **Start Here - Essential Rules for AI Assistants**                 | ✅ Active | CRITICAL |
| [#1](lesson-01.md)  | Branch Protection: Wrong Status Check Context Names                | ✅ Fixed  | CRITICAL |
| [#2](lesson-02.md)  | Signed Commits: `git verify-commit` Doesn't Work in GitHub Actions | ✅ Fixed  | CRITICAL |
| [#3](lesson-03.md)  | Dependency Review: Invalid "proprietary" License Identifier        | ✅ Fixed  | HIGH     |
| [#4](lesson-04.md)  | Dependabot PRs Failed Signed Commits Check                         | ✅ Fixed  | HIGH     |
| [#5](lesson-05.md)  | Dependabot PRs Failed Dependency Review (GitHub Actions Updates)   | ✅ Fixed  | HIGH     |
| [#6](lesson-06.md)  | Branch Protection: Admin Bypass Enabled                            | ✅ Fixed  | CRITICAL |
| [#7](lesson-07.md)  | package-lock.json Must Be Committed (npm Projects)                 | ✅ Fixed  | HIGH     |
| [#8](lesson-08.md)  | REUSE.toml Itself Needs SPDX Headers                               | ✅ Fixed  | MEDIUM   |
| [#9](lesson-09.md)  | Deprecated Dependencies (Jest's glob@7.2.3)                        | ✅ Fixed  | MEDIUM   |
| [#10](lesson-10.md) | Dependency Graph Requires Explicit Activation                      | ✅ Fixed  | MEDIUM   |

### ⚠️ Process Issues (Lessons #11-14)

Common mistakes in development workflow. Important for maintaining quality and consistency.

| #                   | Lesson                                                        | Status        | Priority |
| ------------------- | ------------------------------------------------------------- | ------------- | -------- |
| [#11](lesson-11.md) | Inconsistent Pre-Commit Validation                            | ✅ Documented | MEDIUM   |
| [#12](lesson-12.md) | Ignoring Code Review Comments                                 | ✅ Documented | HIGH     |
| [#13](lesson-13.md) | Using `--admin` to Bypass Branch Protection                   | ✅ Documented | HIGH     |
| [#14](lesson-14.md) | Security Settings Audit: Inconsistencies Between Repositories | ✅ Documented | MEDIUM   |

### 🎯 Meta-Lessons (Lessons #15-17)

Lessons about creating and following lessons. Self-reflective improvements to our process.

| #                   | Lesson                                     | Status         | Priority |
| ------------------- | ------------------------------------------ | -------------- | -------- |
| [#15](lesson-15.md) | Configuration Centralization               | ✅ Implemented | HIGH     |
| [#16](lesson-16.md) | Review Comment Discipline                  | ✅ Implemented | HIGH     |
| [#17](lesson-17.md) | Git State Verification After Work Sessions | ✅ Implemented | MEDIUM   |

### 🔧 Advanced Workflows (Lessons #18-22)

Complex workflow patterns and automation improvements.

| #                   | Lesson                                            | Status         | Priority |
| ------------------- | ------------------------------------------------- | -------------- | -------- |
| [#18](lesson-18.md) | Copilot Review Enforcement System                 | ✅ Implemented | HIGH     |
| [#19](lesson-19.md) | Infinite Copilot Review Loop Prevention           | ✅ Implemented | HIGH     |
| [#20](lesson-20.md) | GitHub Workflow Approval & Rerun                  | ✅ Documented  | MEDIUM   |
| [#21](lesson-21.md) | Branch Protection Check Names Must Match Exactly  | ✅ Implemented | CRITICAL |
| [#22](lesson-22.md) | Reusable Workflow Bootstrap Paradox & GraphQL Fix | ✅ Implemented | HIGH     |

### 🆕 Recent Additions (Lessons #23-29)

Latest lessons from ongoing repository maintenance.

| #                   | Lesson                                                | Status         | Priority |
| ------------------- | ----------------------------------------------------- | -------------- | -------- |
| [#23](lesson-23.md) | Review Workflow Discipline                            | ✅ Implemented | HIGH     |
| [#24](lesson-24.md) | Workflow Error Handling (set -euo pipefail)           | ✅ Implemented | CRITICAL |
| [#25](lesson-25.md) | Meta-Quality: Learning from Recurring Errors          | ✅ Updated     | HIGH     |
| [#26](lesson-26.md) | Dependabot Exception for Copilot Review Enforcement   | ✅ Implemented | MEDIUM   |
| [#27](lesson-27.md) | Script Consolidation & Best Practice Merging          | ✅ Implemented | HIGH     |
| [#28](lesson-28.md) | Professional Communication in Technical Documentation | ✅ Implemented | HIGH     |
| [#29](lesson-29.md) | License Policy is Security-Critical                   | ✅ Documented  | CRITICAL |

## 🔍 How to Use This Index

### Finding Lessons

**By Category:**

- Browse categories above to see lessons by type
- Click lesson number to view full documentation

**By Problem:**
Use the search functionality in your editor to find lessons by keyword:

- Branch protection issues → Lessons #1, #6, #21
- Workflow failures → Lessons #2, #4, #5, #18, #19, #24
- Process/discipline → Lessons #12, #13, #16, #23
- Automation → Lessons #18, #19, #20, #22

**By Priority:**

- **CRITICAL**: Must be fixed immediately (security/blocking issues)
- **HIGH**: Should be fixed soon (quality/reliability issues)
- **MEDIUM**: Should be addressed eventually (improvements)

### Implementing Lessons

Each lesson document contains:

1. **Problem**: What went wrong and why
2. **Solution**: How it was fixed
3. **Action for Future Repos**: Copy-paste implementation steps
4. **Related Lessons**: Cross-references to similar issues

## ✍️ Writing Guidelines

When creating or updating lessons, follow these principles:

- **Use English**: All lessons must be written in English for consistency and accessibility
- **No user quotes**: Document processes and solutions, not conversation history or user feedback
- **Focus on patterns**: Document reusable workflows and patterns, not one-time fixes
- **Self-contained**: Each lesson should be understandable without external context

See [Lesson #25](lesson-25.md) for quality standards and [CONTRIBUTING.md](../../CONTRIBUTING.md) for general contribution guidelines.

## 📊 Statistics

- **Total Lessons**: 30
- **Critical Priority**: 6 (Lessons #1, #2, #6, #21, #24, #29)
- **High Priority**: 14
- **Medium Priority**: 10
- **Implemented**: 27
- **Documented**: 3 (Lessons #20, #25, #29)

## 🔄 Continuous Improvement

This is a living document. New lessons are added as we discover issues across SecPal repositories.

### Recent Updates

- **2025-10-18**: Added [Lesson #29](lesson-29.md) (License Policy is Security-Critical)
- **2025-10-17**: Added [Lesson #28](lesson-28.md) (Professional Communication in Technical Documentation)
- **2025-10-17**: Added [Lesson #27](lesson-27.md) (Script Consolidation & Best Practice Merging)
- **2025-10-17**: Added [Lesson #26](lesson-26.md) (Dependabot Exception for Copilot Review Enforcement)
- **2025-10-17**: Added [Lesson #25](lesson-25.md) (Meta-Quality: Learning from Recurring Errors)
- **2025-10-17**: Added [Lesson #24](lesson-24.md) (Workflow Error Handling)
- **2025-10-17**: Split monolithic LESSONS-LEARNED into individual files
- **2025-10-16**: Cross-repo audit revealed Lesson #21 recurrence

### Contributing

When adding a new lesson:

1. Create `lesson-XX.md` with the template structure
2. Update this README with the lesson entry
3. Update statistics
4. Cross-reference related lessons

## 📖 Related Documentation

- [Lesson Naming Convention](../LESSON-NAMING-CONVENTION.md)
- [Repository Setup Guide](../REPOSITORY-SETUP-GUIDE.md)
- [Cross-Repo Audit (2025-10-16)](../CROSS-REPO-AUDIT-2025-10-16.md)
- [Legacy Lessons Document](../LESSONS-LEARNED-CONTRACTS-REPO.md) (deprecated)

---

**Note:** The original monolithic document `LESSONS-LEARNED-CONTRACTS-REPO.md` is kept for historical reference but should not be updated. All new lessons go into individual files in this directory.
