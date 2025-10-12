<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Lesson Enforcement Strategy: Making Best Practices Automatic

**Date:** 2025-10-12
**Priority:** CRITICAL - Core Infrastructure
**Status:** STRATEGY DOCUMENT
**Context:** User requirement - "wie wir zukünftig (absolut) sicher stellen können, dass die Learned Lessons und die best Practices wirklich eingehalten werden"

---

## The Fundamental Problem

**User's Critical Insight:**

> "Nimm in Deine To-Do also die Überlegung mit auf, wie wir zukünftig (absolut) sicher stellen können, dass die Learned Lessons und die best Practices wirklich eingehalten werden."

**Why This Matters:**

- We documented Lesson #15 (Configuration Centralization) → **Still violated in both repos**
- We documented Lesson #16 (Review Comment Discipline) → **Violated after documentation**
- We now have 213 pages of documentation → **Will it actually be followed?**

**The Hard Truth:**

```
Documentation alone DOES NOT WORK.
Humans forget. Humans skip. Humans are under pressure.
Only TECHNICAL ENFORCEMENT ensures compliance.
```

---

## The Enforcement Pyramid

```
Level 4: IMPOSSIBLE TO VIOLATE   ← Target State
    ↓
Level 3: BLOCKS MERGE (CI/CD)
    ↓
Level 2: WARNS LOUDLY (Pre-commit, Linters)
    ↓
Level 1: DOCUMENTED (README, Guidelines)
    ↓
Level 0: UNDOCUMENTED (Tribal Knowledge)
```

**Current State:** Most lessons at Level 1 (documented)
**Goal:** Move critical lessons to Level 3-4

---

## Strategy: Technical Enforcement Layers

### Layer 1: Pre-Commit Hooks (Immediate Feedback)

**Purpose:** Catch violations BEFORE commit (seconds after writing code)

#### Implementation for Each Lesson

##### Lesson #15 (Configuration Centralization)

**Violation:** Hardcoded licenses in workflows

**Pre-Commit Hook:**

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Check for hardcoded license lists
if git diff --cached -- '*.yml' '*.yaml' | \
   grep -E "^\+.*deny-licenses:|^\+.*allow-licenses:" | \
   grep -v ".license-policy.json" | \
   grep -v "# Lesson #15: Allowed hardcoded"; then

  echo "❌ LESSON #15 VIOLATION: Hardcoded licenses detected!"
  echo ""
  echo "You're trying to commit hardcoded license configuration."
  echo "This violates Lesson #15 (Configuration Centralization)."
  echo ""
  echo "Fix: Load from .license-policy.json dynamically:"
  echo "  DENIED=\$(jq -r '.deniedLicenses | join(\", \")' .license-policy.json)"
  echo ""
  echo "If this is intentionally needed, add comment:"
  echo "  # Lesson #15: Allowed hardcoded (reason: ...)"
  echo ""
  exit 1
fi
```

**Result:** Impossible to commit violation without explicit override.

---

##### Lesson #16 (Review Comment Discipline)

**Violation:** Merging PR with unresolved comments

**Pre-Merge Check (via GitHub Action):**

```yaml
name: Lesson #16 Enforcement

on:
  pull_request:
    types: [opened, synchronize, ready_for_review]
  pull_request_review_comment:

jobs:
  check-review-comments:
    runs-on: ubuntu-latest
    steps:
      - name: Count unresolved conversations
        uses: actions/github-script@v7
        with:
          script: |
            const { data: reviews } = await github.rest.pulls.listReviews({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: context.issue.number
            });

            const { data: comments } = await github.rest.pulls.listReviewComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: context.issue.number
            });

            const unresolved = comments.filter(c => !c.in_reply_to_id);

            if (unresolved.length > 0) {
              core.setFailed(
                `LESSON #16 VIOLATION: ${unresolved.length} unresolved review comment(s).\n` +
                `Per Lesson #16 (Review Comment Discipline), all comments must be:\n` +
                `1. Implemented, OR\n` +
                `2. Explained why not implementing, OR\n` +
                `3. Marked as resolved\n\n` +
                `Unresolved comments:\n` +
                unresolved.map(c => `- Line ${c.line}: ${c.body.substring(0, 50)}...`).join('\n')
              );
            }
```

**Result:** PR cannot be merged with unresolved comments.

---

##### Lesson #17 (DRY - Multi-Repo)

**Violation:** Copying code instead of using templates

**Pre-Commit Hook:**

```bash
# Check for duplicate code patterns
if git diff --cached -- 'scripts/*.sh' | grep -E "^\+.*jq -r.*license"; then
  echo "⚠️  LESSON #17 WARNING: License checking code detected"
  echo ""
  echo "Are you duplicating check-licenses.sh logic?"
  echo "Consider using the shared template:"
  echo "  curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh > scripts/check-licenses.sh"
  echo ""
  echo "Continue anyway? (y/N)"
  read -r response
  if [[ ! "$response" =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi
```

**Result:** Developer prompted before creating duplicate code.

---

##### Lesson #18 (PR Structure)

**Violation:** Mixed concerns in single PR

**GitHub Action:**

```yaml
name: Lesson #18 Enforcement (PR Structure)

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  check-pr-scope:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Analyze PR scope
        run: |
          files=$(git diff --name-only origin/${{ github.base_ref }}...HEAD)

          # Check for mixed file types
          has_workflows=false
          has_scripts=false
          has_docs=false
          has_config=false

          while IFS= read -r file; do
            [[ "$file" =~ ^\.github/workflows/ ]] && has_workflows=true
            [[ "$file" =~ ^scripts/ ]] && has_scripts=true
            [[ "$file" =~ ^docs/ ]] && has_docs=true
            [[ "$file" =~ \.(json|yaml|yml)$ ]] && has_config=true
          done <<< "$files"

          # Count how many categories
          count=0
          [[ "$has_workflows" == true ]] && ((count++))
          [[ "$has_scripts" == true ]] && ((count++))
          [[ "$has_docs" == true ]] && ((count++))
          [[ "$has_config" == true ]] && ((count++))

          if [ $count -ge 3 ]; then
            echo "⚠️  LESSON #18 WARNING: PR touches multiple concerns"
            echo ""
            echo "This PR modifies:"
            [[ "$has_workflows" == true ]] && echo "  - Workflows (.github/workflows/)"
            [[ "$has_scripts" == true ]] && echo "  - Scripts (scripts/)"
            [[ "$has_docs" == true ]] && echo "  - Documentation (docs/)"
            [[ "$has_config" == true ]] && echo "  - Configuration files (*.json, *.yaml)"
            echo ""
            echo "Per Lesson #18 (PR Structure), consider splitting into separate PRs."
            echo "If concerns are tightly coupled, document rationale in PR description."
            echo ""
            echo "Add this label if intentionally combined: 'lesson-18-exception'"
          fi
```

**Result:** Warning issued, but allows override with justification.

---

### Layer 2: CI/CD Enforcement (Blocks Merge)

**Purpose:** Automated checks run on every PR, block merge if violated

#### Centralized Enforcement Workflow

**Location:** `.github/workflows/lesson-enforcement.yml`

```yaml
name: Lesson Enforcement

on:
  pull_request:
    branches: [main, develop]

permissions:
  contents: read
  pull-requests: write

jobs:
  enforce-lessons:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      # Lesson #15: Configuration Centralization
      - name: Check Lesson #15 Compliance
        run: |
          echo "🔍 Checking Lesson #15 (Configuration Centralization)..."

          violations=$(grep -rn "deny-licenses:\|allow-licenses:" .github/workflows/ \
            | grep -v ".license-policy.json" \
            | grep -v "steps.policy.outputs" \
            | grep -v "# Lesson #15: Allowed" || true)

          if [ -n "$violations" ]; then
            echo "❌ LESSON #15 VIOLATION DETECTED"
            echo ""
            echo "$violations"
            echo ""
            echo "See: docs/LESSONS-LEARNED.md#lesson-15"
            exit 1
          fi

          echo "✅ Lesson #15: Compliant"

      # Lesson #16: Review Comment Discipline
      # (Implemented via GitHub Action above)

      # Lesson #17: DRY Compliance
      - name: Check Lesson #17 Compliance
        run: |
          echo "🔍 Checking Lesson #17 (DRY)..."

          # Check if check-licenses.sh differs from template
          if [ -f scripts/check-licenses.sh ]; then
            template=$(curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh)
            current=$(cat scripts/check-licenses.sh)

            if [ "$template" != "$current" ]; then
              echo "⚠️  WARNING: scripts/check-licenses.sh differs from template"
              echo "Consider syncing with shared template."
            fi
          fi

      # Additional lessons as they're created...

      - name: Enforcement Summary
        if: success()
        run: |
          echo "✅ All lessons enforced successfully!"
          echo ""
          echo "Checked:"
          echo "  - Lesson #15 (Configuration Centralization)"
          echo "  - Lesson #16 (Review Comment Discipline)"
          echo "  - Lesson #17 (DRY Multi-Repo)"
```

**Branch Protection:**

```bash
# Make lesson-enforcement required
gh api repos/SecPal/<repo>/branches/main/protection \
  -X PUT \
  --field required_status_checks.contexts[]="enforce-lessons"
```

---

### Layer 3: Architecture Enforcement (Design-Level)

**Purpose:** Make violations architecturally impossible

#### Strategy 1: Eliminate the Option

**Example: Configuration Centralization**

Instead of allowing `deny-licenses` parameter at all:

```yaml
# ❌ OLD: Could be misused
- uses: actions/dependency-review-action@v4
  with:
    deny-licenses: ${{ steps.policy.outputs.denied }}  # Could hardcode here

# ✅ NEW: Reusable workflow, no option to hardcode
jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    # No deny-licenses parameter exposed!
```

**Result:** Literally impossible to violate because the parameter doesn't exist.

---

#### Strategy 2: Automated Synchronization

**Example: DRY Enforcement**

```yaml
# Run nightly: Sync templates to all repos
name: Auto-Sync Templates

on:
  schedule:
    - cron: "0 2 * * *" # 2 AM daily

jobs:
  sync:
    strategy:
      matrix:
        repo: [contracts, api, frontend, backend]
    steps:
      - name: Sync to ${{ matrix.repo }}
        run: |
          # Clone repo
          git clone https://github.com/SecPal/${{ matrix.repo }}
          cd ${{ matrix.repo }}

          # Sync template
          curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh \
            > scripts/check-licenses.sh

          # Create PR if changes detected
          if ! git diff --quiet; then
            git checkout -b sync/templates-$(date +%s)
            git commit -am "chore: sync shared templates"
            git push origin HEAD
            gh pr create --title "chore: Auto-sync templates" --body "Automated template synchronization"
          fi
```

**Result:** Templates automatically kept in sync. Drift auto-corrected.

---

#### Strategy 3: Policy as Code

**Example: Open Policy Agent (OPA)**

```rego
# policies/lessons.rego
package secpal.lessons

# Lesson #15: Deny hardcoded licenses
deny[msg] {
  input.file.path == ".github/workflows/*.yml"
  workflow := yaml.unmarshal(input.file.content)
  job := workflow.jobs[_]
  step := job.steps[_]

  # Check if deny-licenses is hardcoded
  step.with.deny_licenses
  not contains(step.with.deny_licenses, "steps.policy.outputs")

  msg := sprintf(
    "Lesson #15 violation in %s: Hardcoded deny-licenses. Use .license-policy.json",
    [input.file.path]
  )
}

# Lesson #16: Require resolved comments
deny[msg] {
  input.pr.unresolved_comment_count > 0

  msg := sprintf(
    "Lesson #16 violation: %d unresolved review comments. Address all before merge.",
    [input.pr.unresolved_comment_count]
  )
}
```

**Enforcement:**

```yaml
- name: Run OPA Policy Check
  uses: open-policy-agent/opa-action@v2
  with:
    policy: policies/
    input: ${{ toJSON(github) }}
```

---

### Layer 4: Education & Culture (Supporting Layer)

**Purpose:** Help developers WANT to follow lessons

#### 1. Lesson Reference Bot

**GitHub App that comments on PRs:**

```markdown
👋 Hi! I noticed this PR touches license configuration.

Quick reminder: **Lesson #15 (Configuration Centralization)**

- ✅ Use .license-policy.json for license lists
- ❌ Don't hardcode deny-licenses in workflows

Helpful links:

- [Lesson #15 Documentation](https://github.com/SecPal/.github/blob/main/docs/LESSONS-LEARNED.md#lesson-15)
- [Example Implementation](https://github.com/SecPal/.github/pull/17)

Need help? Ask in [Discussions](https://github.com/SecPal/.github/discussions)
```

---

#### 2. Interactive Lesson Onboarding

**New developer checklist:**

```markdown
# SecPal Developer Onboarding

## Core Lessons (Must Read)

- [ ] Lesson #15: Configuration Centralization
  - [ ] Read documentation
  - [ ] Review example: `.github` PR #17
  - [ ] Try exercise: Convert hardcoded config in test repo

- [ ] Lesson #16: Review Comment Discipline
  - [ ] Read documentation
  - [ ] Understand bot comments = human comments
  - [ ] Try exercise: Practice resolving conversations

- [ ] Lesson #17: DRY Multi-Repo
  - [ ] Read documentation
  - [ ] Learn about shared templates
  - [ ] Try exercise: Use template in new repo

## Verification

- [ ] All lessons read
- [ ] Quiz completed (link)
- [ ] First PR created with mentor review
```

---

#### 3. Lesson Badges in PRs

**Auto-comment on PRs:**

```markdown
## 🏆 Lesson Compliance Report

✅ Lesson #15 (Configuration Centralization) - Compliant
✅ Lesson #16 (Review Comment Discipline) - 0 unresolved comments
⚠️ Lesson #17 (DRY) - Warning: Modified shared script
✅ Lesson #18 (PR Structure) - Single concern PR

**Overall: 3/4 passing, 1 warning**

Great job following our lessons! 🎉
```

---

## Implementation Roadmap

### Phase 1: Critical Enforcement (Week 1-2)

**Goal:** Block the most critical violations

- [ ] Add pre-commit hook for Lesson #15 (hardcoded configs)
- [ ] Add CI check for Lesson #15 (blocks merge)
- [ ] Add GitHub Action for Lesson #16 (review comments)
- [ ] Make both required status checks in branch protection
- [ ] Test with mock violations

**Result:** Lessons #15 and #16 technically enforced.

---

### Phase 2: Warning Systems (Week 3-4)

**Goal:** Warn about important but non-critical issues

- [ ] Add pre-commit warnings for Lesson #17 (DRY)
- [ ] Add PR analysis for Lesson #18 (PR structure)
- [ ] Create lesson reference bot
- [ ] Add compliance badges to PRs
- [ ] Monitor false positive rate

**Result:** Developers guided toward best practices.

---

### Phase 3: Architecture Enforcement (Month 2)

**Goal:** Make violations impossible by design

- [ ] Convert all workflows to reusable templates
- [ ] Implement automated template sync
- [ ] Remove hardcoded config options entirely
- [ ] Implement OPA policy engine
- [ ] Create self-healing scripts (auto-fix common issues)

**Result:** Many lessons cannot be violated.

---

### Phase 4: Culture & Tooling (Month 3+)

**Goal:** Comprehensive enforcement ecosystem

- [ ] Build custom GitHub App for enforcement
- [ ] Create interactive lesson training
- [ ] Add lesson compliance metrics to dashboard
- [ ] Implement ML-based pattern detection
- [ ] Create automated fix suggestions

**Result:** Enforcement becomes invisible infrastructure.

---

## Metrics & Success Criteria

### Enforcement Effectiveness

| Lesson             | Violations Before | Violations After | Target |
| ------------------ | ----------------- | ---------------- | ------ |
| #15 (Config)       | 2 repos           | 0                | 0      |
| #16 (Comments)     | 3 PRs             | 0                | 0      |
| #17 (DRY)          | 100% duplication  | <5%              | 0%     |
| #18 (PR Structure) | ~50% mixed        | <20%             | <10%   |

### Developer Experience

- ⏱️ **Time to violation detection:** < 5 seconds (pre-commit)
- 🎯 **False positive rate:** < 5%
- 📚 **Lesson discoverability:** 100% (auto-linked)
- ✅ **Override process:** Clear, documented, tracked

### System Health

- 🔄 **Template sync:** 100% (automated)
- 📊 **Compliance dashboard:** Updated real-time
- 🛡️ **Required checks:** All passing before merge
- 🤖 **Automation coverage:** 80%+ of lessons

---

## Anti-Patterns to Avoid

### ❌ Don't: Enforcement Without Education

```
Problem: Block PR with cryptic "Lesson #15 violated"
Result: Developer confused, frustrated, time wasted
```

**✅ Do: Clear explanation + links**

```
❌ Lesson #15 violated

Why: Hardcoded licenses make updates difficult
Fix: Load from .license-policy.json (example: <link>)
Docs: <link to lesson>
Need help? <link to discussions>
```

---

### ❌ Don't: Too Strict (Block Everything)

```
Problem: Every tiny deviation blocks merge
Result: Developers find workarounds, disable checks
```

**✅ Do: Graduated responses**

```
Level 1: Info message (optional fix)
Level 2: Warning (should fix, but not blocking)
Level 3: Error (blocks merge, must fix or override)
Level 4: Impossible (architecturally prevented)
```

---

### ❌ Don't: Enforcement Without Escape Hatch

```
Problem: Legitimate edge case, no way to override
Result: Process breakdown, emergency admin merge
```

**✅ Do: Documented override process**

```yaml
# Allow override with explanation
deny-licenses: "special-case-license"  # Lesson #15: Allowed (reason: ...)

# Track overrides
if grep "Lesson #15: Allowed"; then
  echo "⚠️  Override detected - will be audited"
  # Log to tracking system
fi
```

---

## Governance

### Who Can Override Enforcement?

**Tier 1: Pre-commit hooks**

- Override: Local disable (developer responsibility)
- Audit: No (local only)

**Tier 2: CI/CD checks**

- Override: Add label `lesson-exception-approved`
- Approval required: 2 maintainers
- Audit: Quarterly review of all exceptions

**Tier 3: Architecture**

- Override: Not possible by design
- Change: Requires RFC + team vote

### Exception Tracking

```markdown
# Exception Log

## Active Exceptions

| PR  | Lesson | Reason                   | Approved By    | Expires    |
| --- | ------ | ------------------------ | -------------- | ---------- |
| #42 | #15    | Emergency hotfix         | @user1, @user2 | 2025-10-20 |
| #53 | #18    | Tightly coupled refactor | @user1, @user3 | Permanent  |

## Past Exceptions (Resolved)

| PR  | Lesson | Reason             | Resolution                |
| --- | ------ | ------------------ | ------------------------- |
| #17 | #18    | Audit PR with docs | Accepted as best practice |
```

---

## Related Documents

- **AUDIT-REPORT-2025-10-12.md:** Documents why we need enforcement
- **PREVENTION-STRATEGY.md:** Overlaps with this, focuses on prevention
- **LESSON-NAMING-CONVENTION.md:** How to document enforceable lessons
- **PR-STRUCTURE-GUIDELINES.md:** Lesson #18 details

---

## Next Actions

### Immediate (This Week)

- [ ] Review this strategy document
- [ ] Approve Phase 1 implementation
- [ ] Create pre-commit hook for Lesson #15
- [ ] Create CI check for Lesson #16
- [ ] Test enforcement on PRs #17

### Short Term (Next 2 Weeks)

- [ ] Roll out Phase 1 to both repos
- [ ] Monitor for false positives
- [ ] Adjust enforcement thresholds
- [ ] Document override process

### Medium Term (Next Month)

- [ ] Implement Phase 2 (warnings)
- [ ] Start Phase 3 (architecture)
- [ ] Create compliance dashboard
- [ ] Train team on enforcement system

---

## Conclusion

**The Core Insight:**

Documentation ≠ Compliance

Only technical enforcement ensures lessons are followed.

**The Strategy:**

1. **Pre-commit:** Immediate feedback (seconds)
2. **CI/CD:** Automated enforcement (minutes)
3. **Architecture:** Make violations impossible (design)
4. **Culture:** Make developers want to comply (education)

**The Result:**

Lessons learned become **infrastructure**, not just **documentation**.

---

**Document Version:** 1.0
**Status:** STRATEGY - Awaiting Implementation
**Last Updated:** 2025-10-12
**User Requirement:** "absolut sicher stellen, dass die Learned Lessons ... wirklich eingehalten werden"
**Priority:** CRITICAL - Without this, all other documentation is just hope.
