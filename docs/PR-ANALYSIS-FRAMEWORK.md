<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# PR Analysis Framework

**Purpose:** Systematic analysis of all historical PRs to identify preventable patterns
**Date Started:** 2025-10-18
**Scope:** All .github repository PRs (#1 - #59)
**Goal:** Reduce future PR cycles from 3 → 1-2, nitpicks from 30% → 10%

---

## Analysis Methodology

### Data Collection

For each PR, collect:

1. **Basic Metrics**
   - PR number, title, state (merged/closed)
   - Review cycle count (number of Copilot reviews)
   - Total comment count
   - Time from creation to merge

2. **Comment Classification**
   - CRITICAL: Security, data loss, breaking bugs
   - HIGH: Functional bugs, incorrect behavior
   - MEDIUM: Code quality, maintainability
   - LOW: Style, minor inconsistencies (nitpicks)

3. **Pattern Identification**
   - Recurring comment themes
   - Preventable via automation (pre-commit hooks, linters)
   - Preventable via documentation (lessons, checklists)
   - Unavoidable (genuine code review insights)

4. **Root Cause**
   - Missing automation
   - Unclear documentation
   - Knowledge gap
   - Time pressure/shortcuts
   - First-time occurrence (acceptable)

### Analysis Phases

#### Phase 1: Recent PRs (Copilot Review Era)

**Scope:** PRs #42+ (2025-10-15 onward - after Lesson #18 implementation)
**Focus:** Patterns DESPITE enforcement being active
**Value:** High - these show current gaps

#### Phase 2: Pre-Enforcement PRs

**Scope:** PRs #18-#41 (if Copilot reviewed manually)
**Focus:** What enforcement prevented vs what still leaks through
**Value:** Medium - historical context

#### Phase 3: Early PRs

**Scope:** PRs #1-#17 (early lessons learned)
**Focus:** Bootstrap issues, foundational patterns
**Value:** Low - most already documented in LESSONS-LEARNED

---

## Data Structure

```markdown
### PR #XX: Title

**Metrics:**

- Review cycles: X
- Total comments: Y
- Classification: Z CRITICAL / A HIGH / B MEDIUM / C LOW
- Time to merge: D hours

**Comment Patterns:**

1. **Pattern Name** (Priority Level - Count)
   - Description of recurring issue
   - Example: "Hardcoded values instead of variables (MEDIUM - 3)"
   - Preventable: Yes/No
   - How: automation/documentation/unavoidable

**Root Causes:**

- Primary: [missing automation/unclear docs/knowledge gap]
- Contributing factors

**Learnings:**

- What could prevent this in future?
- Automation opportunity?
- Documentation gap?

---
```

## Pattern Categories (Initial Taxonomy)

### Code Quality

- Hardcoded values
- Missing error handling
- Inconsistent naming
- Missing comments/documentation

### Bash Scripting

- Missing `set -euo pipefail`
- No trap cleanup
- Single quotes in variable expansion
- Missing nullglob for globs

### Documentation

- Hardcoded PR numbers in examples
- Hardcoded repo names
- Broken cross-references
- User quotes in lessons

### GraphQL/API

- PRRT*\* vs PRRC*\* confusion
- Pagination insufficient
- Missing variable parameterization

### Workflow

- Forgotten review requests
- Premature thread resolution
- Skipping pre-commit checks

### Lessons/Meta

- Incomplete factual verification
- Superficial pattern fixes (only one instance)
- Missing cross-references

---

## Success Metrics

**Target Outcomes:**

| Metric             | Current (PR #58 baseline) | Target    | Measurement                             |
| ------------------ | ------------------------- | --------- | --------------------------------------- |
| Review cycles      | 3                         | 1-2       | Average of next 10 PRs                  |
| Nitpick %          | 30%                       | 10%       | LOW-priority comments / total           |
| Preventable errors | Unknown                   | <20%      | Comments addressable by automation/docs |
| Time per cycle     | 30-60 min                 | 15-30 min | Contributor self-reporting              |

**Deliverables:**

1. **Pattern Report** (this document + analysis)
2. **Automation Recommendations** (2-3 new tools/scripts)
3. **Documentation Gaps** (lessons to create)
4. **Pre-commit Enhancements** (additional checks)

---

## Analysis Status

- [ ] Phase 1: Recent PRs (#42-#59) - 18 PRs
- [ ] Phase 2: Pre-enforcement (#18-#41) - 24 PRs
- [ ] Phase 3: Early PRs (#1-#17) - 17 PRs
- [ ] Pattern consolidation
- [ ] Recommendations report
- [ ] Implementation plan

**Next Action:** Start with PR #59 (current), work backward chronologically

---

**Maintained In:** `.github/docs/PR-ANALYSIS-FRAMEWORK.md`
**Last Updated:** 2025-10-18
