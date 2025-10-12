<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson Naming Convention

**Date:** 2025-10-12
**Status:** PROPOSAL - Needs Decision
**Context:** User feedback on PR# based numbering not being intuitive

---

## Problem Statement

Current lessons are numbered sequentially based on PR order:

- Lesson #15: Configuration Centralization (from `.github` PR #13)
- Lesson #16: Review Comment Discipline (from `.github` PR #14)

**User Concern:**

> "I'm not sure how useful it is to name the rules by PR #. On one hand, directly traceable. On the other hand, when more PRs and possibly points are added... Not intuitive."

**Core Issue:** Numbers alone don't convey meaning. New developer sees "Lesson #15" and has no idea what it's about without reading the full document.

---

## Current System Analysis

### ✅ What Works

1. **Traceability:** `Lesson #15` → Can quickly find when/why it was created (PR #13)
2. **Unique IDs:** Numbers are unambiguous references in code/docs
3. **Sequential:** Clear ordering of when lessons were learned
4. **Already Thematic:** Names are descriptive ("Configuration Centralization")

### ❌ What Doesn't Work

1. **Not Self-Documenting:** "Check Lesson #15" requires lookup
2. **Memory Load:** Developers must memorize number-to-concept mapping
3. **Scalability:** With 50+ lessons, remembering numbers becomes impossible
4. **Search Unfriendly:** Can't search codebase for "configuration" and find "Lesson #15"

---

## Options Analysis

### Option A: Keep Current System (Number + Name)

**Format:**

```
Lesson #15: Configuration Centralization
Lesson #16: Review Comment Discipline
Lesson #17: Systematic Code Audits
```

**Pros:**

- ✅ No changes needed
- ✅ Unique numeric IDs
- ✅ Clear chronological order

**Cons:**

- ❌ Not intuitive when referenced by number alone
- ❌ Doesn't scale well (Lesson #47?)
- ❌ Forces memorization

**Code Reference Example:**

```yaml
# Lesson #15: Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

---

### Option B: Pure Thematic Names (No Numbers)

**Format:**

```
Lesson: Configuration Centralization
Lesson: Review Comment Discipline
Lesson: Systematic Code Audits
```

**Pros:**

- ✅ Self-documenting
- ✅ Intuitive and searchable
- ✅ Scales well (names can be meaningful at any scale)

**Cons:**

- ❌ No unique short reference
- ❌ Names can be long/verbose
- ❌ Harder to reference in code comments (must use full name)

**Code Reference Example:**

```yaml
# Lesson "Configuration Centralization": Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

---

### Option C: Hybrid (Number + Name, Always Together)

**Format:**

```
Lesson #15 (Configuration Centralization)
Lesson #16 (Review Comment Discipline)
Lesson #17 (Systematic Code Audits)
```

**Reference Rules:**

- In code comments: Always include both number AND name
- In documentation: Full format with context
- In discussions: Can use either, but prefer name

**Pros:**

- ✅ Best of both worlds: Unique ID + Meaning
- ✅ Self-documenting when used correctly
- ✅ Flexible reference (use number if everyone knows it)

**Cons:**

- ⚠️ Requires discipline to always include both
- ⚠️ More verbose in comments

**Code Reference Example:**

```yaml
# Lesson #15 (Configuration Centralization): Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

---

### Option D: Semantic Namespacing (Category + Name)

**Format:**

```
Lesson [Config]: Centralization
Lesson [Review]: Comment Discipline
Lesson [Process]: Systematic Code Audits
Lesson [DRY]: Multi-Repo Architecture
```

**Pros:**

- ✅ Self-organizing by category
- ✅ Intuitive grouping
- ✅ Scales to hundreds of lessons
- ✅ Easy to find related lessons

**Cons:**

- ❌ More complex system
- ❌ Need to define and maintain categories
- ❌ Longer references

**Code Reference Example:**

```yaml
# Lesson [Config/Centralization]: Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

---

### Option E: Wiki-Style (Descriptive + Backlink)

**Format:**

```
Configuration Centralization Lesson
  (Learned in: .github PR #13, 2025-10-12)
  (Applied in: contracts PR #14, .github workflows)
```

**Pros:**

- ✅ Completely self-documenting
- ✅ Full context embedded
- ✅ No arbitrary numbering

**Cons:**

- ❌ Very verbose for references
- ❌ Harder to maintain (more metadata)
- ❌ No short reference form

---

## Recommendation: **Option C (Hybrid)** with Guidelines

### Naming Convention

**Full Format:**

```
Lesson #<number> (<Descriptive Name>)
```

**Examples:**

```
Lesson #15 (Configuration Centralization)
Lesson #16 (Review Comment Discipline)
Lesson #17 (Systematic Code Audits)
Lesson #18 (DRY in Multi-Repo Architecture)
```

### Usage Guidelines

#### 1. In Code Comments (Always Include Both)

```yaml
# Lesson #15 (Configuration Centralization): Use centralized config
- name: Load license policy
  run: |
    DENIED=$(jq -r '.deniedLicenses' .license-policy.json)
```

#### 2. In Documentation (Full Context)

```markdown
## Lesson #15: Configuration Centralization

**Origin:** `.github` PR #13 (2025-10-10)
**Category:** Configuration Management
**Impact:** All SecPal repositories

### Problem

Hardcoded configuration values scattered across workflows...
```

#### 3. In Commit Messages (Number + Short Reference)

```
fix: implement Lesson #15 (config centralization)

Load deny-licenses dynamically from .license-policy.json
instead of hardcoding in workflow.
```

#### 4. In Discussions/Chat (Flexible)

```
# All acceptable:
"Did you check Lesson #15?"
"Apply the Configuration Centralization lesson"
"See Lesson #15 (Configuration Centralization)"
```

#### 5. In Cross-References (Number Preferred)

```markdown
See also:

- Lesson #15 (Configuration Centralization)
- Lesson #16 (Review Comment Discipline)
  Related: Lesson #18 (DRY)
```

---

## Implementation Plan

### Phase 1: Document Convention (Week 1)

- [x] Create this document
- [ ] Update LESSONS-LEARNED.md with naming convention
- [ ] Add examples to existing lessons

### Phase 2: Standardize Existing Lessons (Week 1-2)

- [ ] Review all current lesson references in codebase
- [ ] Update code comments to include both number and name
- [ ] Add category/origin metadata to each lesson

### Phase 3: Enforce in Future (Ongoing)

- [ ] Add to PR template: "If creating new lesson, use Lesson #X (Name) format"
- [ ] Add to contributing guide
- [ ] Code review checklist: "Are lesson references properly formatted?"

---

## Examples of Good vs. Bad References

### ❌ BAD (Number Only)

```yaml
# Lesson #15
deny-licenses: ${{ steps.policy.outputs.denied }}
```

**Problem:** Requires developer to look up what Lesson #15 means.

### ⚠️ OKAY (Name Only)

```yaml
# Configuration Centralization: Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

**Problem:** No reference to lesson documentation.

### ✅ GOOD (Hybrid)

```yaml
# Lesson #15 (Configuration Centralization): Load from .license-policy.json
deny-licenses: ${{ steps.policy.outputs.denied }}
```

**Perfect:** Self-documenting AND traceable.

### ✅ EXCELLENT (Hybrid + Context)

```yaml
# Lesson #15 (Configuration Centralization)
# Learned from: Audit 2025-10-12 - hardcoded licenses in workflows
# Load deny-licenses dynamically from centralized config
- name: Load license policy
  id: policy
  run: |
    DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)
    echo "denied=$DENIED" >> $GITHUB_OUTPUT
```

**Perfect:** Complete context for future maintainers.

---

## Naming Best Practices

### Creating New Lesson Names

**DO:**

- ✅ Use active voice: "Centralization" not "Centralize Things"
- ✅ Be specific: "Configuration Centralization" not just "Centralization"
- ✅ Keep under 5 words if possible
- ✅ Use domain terminology: "Review Comment Discipline" not "Fix Comments"

**DON'T:**

- ❌ Use vague names: "Best Practices" (too generic)
- ❌ Use PR numbers in name: "PR #13 Lesson" (redundant)
- ❌ Use dates in name: "October 2025 Config Lesson" (irrelevant)
- ❌ Use jokes/memes: "Config-pocalypse Prevention" (not searchable)

### Examples of Good Names

```
✅ Configuration Centralization
✅ Review Comment Discipline
✅ Systematic Code Audits
✅ DRY in Multi-Repo Architecture
✅ SPDX Compliance Best Practices
✅ Error Handling in Shell Scripts
```

### Examples of Bad Names

```
❌ Lesson About Configs          (too vague)
❌ The One Where We Fix Reviews  (too informal)
❌ PR #13 Config Stuff           (uses PR# in name)
❌ Things We Learned             (not specific)
❌ YOLO Config Management        (unprofessional)
```

---

## Migration Path for Existing Lessons

### Current State

```
docs/LESSONS-LEARNED-CONTRACTS-REPO.md:
  - Lesson #15: Configuration Centralization (Line 872)
  - Lesson #16: Review Comment Discipline (Line 1011)
```

### After Migration

```markdown
## Lesson #15: Configuration Centralization

**Category:** Configuration Management
**Origin:** `.github` PR #13 (2025-10-10)
**Applies To:** All repositories
**Status:** Active

**Alternative Names:**

- Config Centralization
- Centralized Configuration Pattern
- Single Source of Truth for Config

**Keywords:** configuration, centralization, .license-policy.json, hardcoded values
```

**Benefit:** Multiple search terms, clear metadata, easy to find.

---

## FAQ

### Q: Do I always need to write the full format?

**A:** In code comments, yes. In conversation, you can use either number or name, but prefer name for clarity.

### Q: What if the name is too long?

**A:** Keep core name under 5 words. Add details in lesson description, not in name.

### Q: Can I rename an existing lesson?

**A:** Yes, but:

1. Keep the number (for traceability)
2. Update all references in codebase
3. Document the rename in lesson history
4. Add old name as "Alternative Name"

### Q: What if two lessons have similar names?

**A:** Add differentiating context:

```
Lesson #15 (Configuration Centralization - Workflows)
Lesson #23 (Configuration Centralization - Scripts)
```

Or use categories:

```
Lesson #15 [Config]: Workflow Centralization
Lesson #23 [Config]: Script Centralization
```

---

## Decision Required

**Please decide:**

1. ✅ **Option C (Hybrid)** - Number + Name always together
2. ⬜ **Option B (Pure Names)** - No numbers, just descriptive names
3. ⬜ **Option D (Semantic)** - Category-based namespacing
4. ⬜ **Other** - Propose alternative system

**Once decided:**

- Update LESSONS-LEARNED.md with convention
- Add to CONTRIBUTING.md
- Update all existing references in codebase
- Add to PR template

---

## Related Documents

- **Lessons Learned:** `LESSONS-LEARNED-CONTRACTS-REPO.md` (contains current lessons)
- **Contributing Guide:** `CONTRIBUTING.md` (should document this convention)
- **PR Template:** `.github/pull_request_template.md` (should enforce format)

---

**Document Version:** 1.0
**Status:** PROPOSAL - Awaiting Decision
**Last Updated:** 2025-10-12
**Next Action:** User decision on preferred option
