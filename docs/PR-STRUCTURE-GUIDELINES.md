<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Pull Request Structure and Merge Discipline

**Date:** 2025-10-12
**Status:** GUIDELINE - Active
**Context:** User feedback on PR scope and merge discipline

---

## Problem Statement

**User Concern:**

> "We shouldn't only review PRs more critically and audit them before merge and pay attention to comments... We should also make cleaner / more separated / more thematic PRs. It's of course possible to throw a script change and then documentation extension and at the same time another repo change into one PR. But is that sensible?"

**Core Issues:**

1. **Mixed Concerns:** PRs combining workflows + scripts + documentation + config changes
2. **Review Complexity:** Harder to review when multiple unrelated changes in one PR
3. **Rollback Risk:** If one part has issues, must rollback everything
4. **Merge Pressure:** "And if we afterwards have to open five PRs to correct one (hasty) PR merge..."

---

## Fundamental Principle

### The Atomic PR Rule

```
One PR = One Logical Change
```

**A "logical change" is:**

- ✅ A single feature
- ✅ A single bug fix
- ✅ A single refactoring
- ✅ A single documentation update

**NOT:**

- ❌ Multiple unrelated fixes
- ❌ Feature + refactoring + docs
- ❌ "Everything from today's work"

---

## Guidelines by Change Type

### 1. Bug Fixes

#### ✅ GOOD: Single, Focused Fix

```
Title: fix: correct SPDX identifier in contracts/.license-policy.json

Changes:
- contracts/.license-policy.json (GPL-3.0 → GPL-3.0-or-later)

Why: Addresses unaddressed review comment from PR #14 about SPDX format.
```

#### ❌ BAD: Mixed Bug Fixes

```
Title: fix: various issues from audit

Changes:
- .license-policy.json (SPDX format)
- check-licenses.sh (error handling)
- dependency-review.yml (dynamic loading)

Why BAD: Three independent bugs. Should be three PRs.
```

---

### 2. Feature Implementation

#### ✅ GOOD: Single Feature

```
Title: feat: add pre-commit hook for hardcoded config detection

Changes:
- .github/templates/pre-commit (new file)
- docs/CONTRIBUTING.md (installation instructions)
- README.md (mention in setup section)

Why: All changes directly support the single feature.
```

#### ❌ BAD: Multiple Features

```
Title: feat: add pre-commit hooks and reusable workflows

Changes:
- .github/templates/pre-commit
- .github/.github/workflows/reusable-dependency-review.yml
- scripts/sync-templates.sh
- docs/multiple files

Why BAD: Two separate features. Should be two PRs.
```

---

### 3. Documentation

#### ✅ GOOD: Cohesive Documentation

```
Title: docs: comprehensive audit report and prevention strategy

Changes:
- docs/AUDIT-REPORT-2025-10-12.md
- docs/PREVENTION-STRATEGY.md
- docs/ACTION-ITEMS.md

Why: All docs related to single audit event. Cohesive story.
```

#### ❌ BAD: Unrelated Docs

```
Title: docs: various updates

Changes:
- docs/AUDIT-REPORT.md
- docs/API-GUIDE.md
- docs/USER-MANUAL.md

Why BAD: Unrelated documents. Should be separate PRs.
```

---

### 4. Refactoring

#### ✅ GOOD: Focused Refactoring

```
Title: refactor: extract license policy loading to reusable action

Changes:
- .github/actions/load-license-policy/action.yml (new)
- .github/workflows/dependency-review.yml (uses new action)
- .github/workflows/license-check.yml (uses new action)

Why: Single refactoring goal: DRY for license policy loading.
```

#### ❌ BAD: Refactoring + Feature

```
Title: refactor: improve workflows and add new checks

Changes:
- Extract reusable action
- Add new security workflow
- Update existing workflows
- Add documentation

Why BAD: Refactoring + new feature. Should be two PRs.
```

---

## Special Cases: When to Combine Changes

### Exception 1: Tightly Coupled Changes

**Acceptable to combine when:**

1. Changes are **technically dependent** on each other
2. Cannot be tested separately
3. Tell a single coherent story

#### ✅ EXAMPLE: Config + Workflow Using It

```
Title: fix: implement Lesson #15 (Configuration Centralization)

Changes:
- .license-policy.json (ensure correct format)
- .github/workflows/dependency-review.yml (load from config)

Justification:
- Workflow depends on config file existing and being correct
- Cannot test workflow without correct config
- Single logical change: "Move from hardcoded to centralized"
```

**Key:** Document why combined in PR description!

---

### Exception 2: Cascading Fixes

**Acceptable when:**

1. First fix reveals second issue
2. Second issue blocks testing of first
3. Both fixes required for system to work

#### ✅ EXAMPLE: SPDX Fix + Workflow Fix

```
Title: fix: SPDX format + workflow dynamic loading

Changes:
- .license-policy.json (GPL-3.0 → GPL-3.0-or-later)
- .github/workflows/dependency-review.yml (load dynamically)

Justification:
- SPDX fix is prerequisite for dynamic loading to work correctly
- Testing workflow requires correct SPDX format in config
- Fixing separately would require two test runs
```

---

### Exception 3: Breaking Change + Migration

**Acceptable when:**

1. Breaking change requires code updates
2. Updates must ship together
3. Cannot have intermediate broken state

#### ✅ EXAMPLE: Script Signature Change

```
Title: refactor: standardize error handling pattern

Changes:
- scripts/check-licenses.sh (new error handling)
- .github/workflows/license-check.yml (expect new exit codes)
- contracts/scripts/check-licenses.sh (sync implementation)

Justification:
- Changed exit code behavior (breaking change)
- Workflow must be updated to handle new codes
- Sync both repos to maintain consistency
```

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: "Everything from Today"

```
Title: chore: daily updates

Changes:
- 15 files across 5 directories
- Bug fixes + features + docs + refactoring

Problem:
- Impossible to review effectively
- Can't identify what actually changed
- Rollback would undo too much
```

**Fix:** Create separate PRs for each logical change throughout the day.

---

### ❌ Anti-Pattern 2: "While I'm Here..."

```
Title: fix: correct typo in README

Changes:
- README.md (typo fix)
- scripts/deploy.sh (unrelated improvement)
- .github/workflows/ci.yml (optimization)

Problem:
- Original issue (typo) lost in noise
- Reviewer confused about PR purpose
- Unrelated changes slip through
```

**Fix:** Stick to the stated purpose. File separate issues for "while I'm here" improvements.

---

### ❌ Anti-Pattern 3: "Emergency Fixes"

```
Title: URGENT: fix production

Changes:
- Critical security fix
- Performance improvements
- Code cleanup
- Update dependencies

Problem:
- Security fix should be isolated
- Mixing critical + nice-to-have
- Hard to fast-track just the urgent part
```

**Fix:** Separate critical fix (merge immediately) from improvements (normal review).

---

## PR Size Guidelines

### Size Categories

| Size       | Changes       | Review Time   | When Acceptable               |
| ---------- | ------------- | ------------- | ----------------------------- |
| **Tiny**   | 1-10 lines    | 5 minutes     | Typo fixes, config tweaks     |
| **Small**  | 10-50 lines   | 15 minutes    | Bug fixes, small features     |
| **Medium** | 50-200 lines  | 30-60 minutes | Features, refactoring         |
| **Large**  | 200-500 lines | 2+ hours      | Major features, complex fixes |
| **Huge**   | 500+ lines    | Half day+     | Almost never acceptable       |

### Red Flags

**🚨 Automatic Review Triggers:**

- 500+ lines changed
- 10+ files modified
- Changes across 5+ directories
- Mix of languages (e.g., YAML + Bash + Markdown + JSON)

**Action:** Consider splitting into multiple PRs.

---

## PR Structure Checklist

Before creating PR, ask:

### The "One Thing" Test

- [ ] Can I describe this PR in one sentence?
- [ ] Does the title complete: "This PR will..."?
- [ ] Are all changes related to that one goal?

### The "Rollback" Test

- [ ] If we need to revert, would we want to revert ALL these changes?
- [ ] Or would we want to keep some and revert others?
- [ ] If "keep some," split into multiple PRs

### The "Review" Test

- [ ] Can a reviewer understand all changes in 30-60 minutes?
- [ ] Do changes require context-switching between concepts?
- [ ] Would splitting make review easier?

### The "Story" Test

- [ ] Does the git history tell a clear story?
- [ ] Could someone bisect to find this specific change?
- [ ] Is it obvious why these changes go together?

---

## Workflow: From Audit to PRs

### Example: The 2025-10-12 Audit

**What We Did (Single PR):**

```
PR #17: Audit 2025-10-12 - Lesson #15 (Configuration Centralization) Compliance + Documentation

Changes:
- .github/workflows/dependency-review.yml (dynamic loading)
- scripts/check-licenses.sh (error handling)
- docs/AUDIT-REPORT-2025-10-12.md (38 pages)
- docs/PREVENTION-STRATEGY.md (65 pages)
- docs/ACTION-ITEMS.md (5 pages)
```

**What We Could Have Done (Separate PRs):**

#### Option A: Separate by Type

```
PR #17: fix: implement Lesson #15 in dependency-review.yml
  - Only workflow changes
  - Focused, easy to review

PR #18: fix: add error handling to check-licenses.sh
  - Only script changes
  - Independent fix

PR #19: docs: audit report and prevention strategy
  - Only documentation
  - Can be reviewed by different person
```

#### Option B: Separate by Urgency

```
PR #17 (URGENT): fix: critical Lesson #15 (Configuration Centralization) violations
  - dependency-review.yml
  - check-licenses.sh
  - Tag: needs-immediate-merge

PR #18 (NORMAL): docs: comprehensive audit documentation
  - All documentation files
  - Can wait for thorough review
```

#### Option C: Single PR with Clear Sections

```
PR #17: Audit 2025-10-12 Results - Fixes + Documentation

Description organized by concern:

## 1. Critical Fix: Lesson #15 (Configuration Centralization) Compliance
- .github/workflows/dependency-review.yml
- Rationale: Hardcoded config violates lesson

## 2. High Priority: Error Handling
- scripts/check-licenses.sh
- Rationale: Security risk from missing validation

## 3. Documentation
- docs/AUDIT-REPORT-2025-10-12.md
- docs/PREVENTION-STRATEGY.md
- docs/ACTION-ITEMS.md
- Rationale: Record findings for future work

Each section can be reviewed independently.
Commits organized by section.
```

**In This Case:** Option C is acceptable because:

1. All changes stem from single audit event
2. Documentation depends on understanding the fixes
3. Comprehensive PR tells complete story
4. Commits are well-organized by concern

**Key:** Clear organization and justification in PR description.

---

## Commit Message Guidelines

### Atomic Commits Within PR

**Each commit should:**

- Be a single logical unit
- Build successfully
- Pass tests
- Have descriptive message

#### ✅ GOOD Commit History

```
feat: add dynamic license policy loading
fix: add error handling to policy validation
docs: document configuration centralization
test: add tests for policy loading
```

#### ❌ BAD Commit History

```
WIP
fix
more fixes
actually works now
forgot semicolon
```

---

## Merge Strategy

### When to Merge

**Merge checklist:**

- [ ] All CI checks passing
- [ ] All review comments addressed (Lesson #16!)
- [ ] No unresolved conversations
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] At least one approval (if team size > 1)

### When to Split Instead

**Consider splitting if:**

- [ ] PR has been open > 1 week with no progress
- [ ] Reviewers asking to split concerns
- [ ] Part of PR is urgent, part can wait
- [ ] PR grew beyond original scope
- [ ] Multiple independent concerns discovered

**How to split:**

1. Create new branch from original base
2. Cherry-pick relevant commits
3. Create new PR with focused scope
4. Close or update original PR

---

## Templates and Examples

### Small Bug Fix Template

```markdown
## Summary

Single-line description of what this fixes.

## Problem

What was broken? How did we discover it?

## Solution

What changed? Why is this the right fix?

## Testing

How was this validated?

## Related Issues

Closes #123
Addresses review comments from PR #456
```

### Feature Implementation Template

```markdown
## Summary

What does this feature do?

## Motivation

Why do we need this feature?

## Implementation

High-level overview of approach.

## Changes

- File 1: What changed and why
- File 2: What changed and why

## Testing

- [ ] Unit tests added
- [ ] Integration tests added
- [ ] Manual testing completed

## Documentation

- [ ] README updated
- [ ] API docs updated
- [ ] Examples added
```

### Refactoring Template

```markdown
## Summary

What is being refactored and why?

## Before

How did it work before? What was the problem?

## After

How does it work now? What improved?

## Behavior Changes

List any behavior changes (should be minimal).

## Migration Required

Is any action needed by users/developers?
```

---

## Real-World Examples

### ✅ Example 1: contracts PR #14 (Original)

**Title:** `fix: centralize license policy in config file`

**Changes:**

- `.license-policy.json` (new file)
- `package.json` (add jq dependency reference)
- `scripts/check-licenses.sh` (read from .license-policy.json)

**Analysis:** ✅ Good!

- Single goal: Centralize license configuration
- All changes support that goal
- Cohesive and reviewable

**Issue:** Unaddressed review comments (Lesson #16 violation)

---

### ✅ Example 2: .github PR #15 (Original)

**Title:** `fix: address unresolved review comments from PR #14`

**Changes:**

- `scripts/validate-config.sh` (add validation)
- `docs/LESSONS-LEARNED.md` (document Lesson #16)

**Analysis:** ✅ Good!

- Single goal: Address previous feedback
- Creates new lesson from the experience
- Clear traceability

---

### ✅ Example 3: Hypothetical Good Split

**Scenario:** Discovered 3 issues during audit

**PR #A:**

```
Title: fix: correct SPDX format in license policy
Files: .license-policy.json
Why: Atomic fix, easy to review, can merge immediately
```

**PR #B:**

```
Title: fix: add error handling to check-licenses.sh
Files: scripts/check-licenses.sh
Why: Independent improvement, different concern than SPDX
Depends on: PR #A (needs correct policy file to test)
```

**PR #C:**

```
Title: fix: implement dynamic config loading in workflow
Files: .github/workflows/dependency-review.yml
Why: Lesson #15 (Configuration Centralization) enforcement
Depends on: PR #A (needs correct policy format)
```

**Benefit:**

- Each can be reviewed independently
- Can merge A immediately if critical
- Clear dependencies documented
- Easy to rollback any specific change

---

## Decision Framework

### Use This Flow Chart

```
Found multiple issues during work
        ↓
Are they tightly coupled?
├─ YES → Single PR with clear sections
└─ NO → Multiple PRs
        ↓
Can they be tested independently?
├─ YES → Definitely separate PRs
└─ NO → Consider single PR, document coupling
        ↓
Does separating improve review quality?
├─ YES → Separate
└─ NO → Can combine, but explain why
```

---

## Enforcement

### PR Review Checklist

**Reviewers should ask:**

- [ ] Is scope clear from title?
- [ ] Are all changes related to stated goal?
- [ ] Would splitting make review easier?
- [ ] Can this be safely reverted as a unit?
- [ ] Are review comments being addressed?

**If answer is NO to any:**

- Request split into multiple PRs
- Provide clear guidance on how to split
- Be respectful but firm

### Automation Opportunities

**Future:** Add GitHub Action to:

- Flag PRs with >500 lines
- Flag PRs modifying >10 files
- Flag PRs with mixed file types (YAML + code + docs)
- Suggest splitting criteria

---

## Summary

### Core Principles

1. **One PR = One Logical Change**
2. **Atomic commits within PR**
3. **Address ALL review comments (Lesson #16)**
4. **Document exceptions clearly**
5. **When in doubt, split**

### Benefits

- ✅ Easier code review
- ✅ Safer merges
- ✅ Simpler rollbacks
- ✅ Clearer git history
- ✅ Faster iterations

### Red Flags

- 🚨 "Various updates" in title
- 🚨 500+ lines changed
- 🚨 Multiple unrelated files
- 🚨 Mixing critical + nice-to-have

---

## Related Documents

- **Lesson #16 (Review Comment Discipline):** Review Comment Discipline
- **CONTRIBUTING.md:** General contribution guidelines
- **CODE_REVIEW_GUIDE.md:** Detailed review practices

---

**Document Version:** 1.0
**Status:** GUIDELINE - Active
**Last Updated:** 2025-10-12
**Next Review:** After 10 PRs, assess if guidelines are being followed
