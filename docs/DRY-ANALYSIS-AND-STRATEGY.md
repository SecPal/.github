<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# DRY Analysis and Multi-Repo Strategy

**Date:** 2025-10-12
**Priority:** HIGH - Fundamental architectural principle
**Related:** AUDIT-REPORT-2025-10-12.md, PREVENTION-STRATEGY.md

---

## Problem Statement

During the 2025-10-12 audit, identical fixes were made in **both** `.github` and `contracts` repositories:

- Identical `check-licenses.sh` scripts (32 lines, 100% duplicate)
- Nearly identical `dependency-review.yml` workflows
- Similar error handling patterns
- Duplicate implementation effort

**This violates DRY (Don't Repeat Yourself) principles**, especially critical for multi-repo architectures.

---

## Current State: Code Duplication Analysis

### 1. ✅ IDENTICAL CODE (100% Duplicate)

#### `scripts/check-licenses.sh`

**Location:**

- `.github/scripts/check-licenses.sh`
- `contracts/scripts/check-licenses.sh`

**Code:** 32 lines, byte-for-byte identical

```bash
#!/bin/bash
# ... SPDX headers ...

# Check if .license-policy.json exists
if [ ! -f .license-policy.json ]; then
  echo "No .license-policy.json found, skipping license check."
  exit 0
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
  echo "Error: jq is required but not installed!" >&2
  exit 1
fi

# ... (remaining 20 lines identical) ...
```

**DRY Violation:** Maintenance nightmare. Bug fix required in 2 places.

---

### 2. ⚠️ NEAR-IDENTICAL CODE (95% Duplicate)

#### `.github/workflows/dependency-review.yml`

**Differences:**

- `contracts` has Dependabot workflow-only skip logic (14 lines)
- Otherwise identical (license policy loading, error handling)

**Shared Logic (22 lines):**

```yaml
- name: Load license policy
  id: policy
  run: |
    if [ ! -f .license-policy.json ]; then
      echo "Error: .license-policy.json not found!" >&2
      exit 1
    fi
    DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)
    if [ -z "$DENIED" ]; then
      echo "Error: deniedLicenses is empty!" >&2
      exit 1
    fi
    echo "denied=$DENIED" >> $GITHUB_OUTPUT

- name: Dependency Review
  uses: actions/dependency-review-action@v4
  with:
    deny-licenses: ${{ steps.policy.outputs.denied }}
```

**DRY Violation:** 95% of workflow logic duplicated.

---

### 3. 🟡 SIMILAR BUT INTENTIONALLY DIFFERENT

#### `.license-policy.json`

**Must be different** (different projects, different license needs):

- `.github` allows: `WTFPL`, `Python-2.0`
- `contracts` allows: `GPL-3.0-or-later`, `LGPL-3.0-or-later`, `AGPL-3.0-or-later`

**However:** Common base licenses exist (MIT, Apache-2.0, BSD, ISC, etc.)

**Opportunity:** Split into `common-base.json` + repo-specific additions

---

### 4. 📚 DOCUMENTATION ASYMMETRY

**Current State:**

- `.github/docs/` contains 108 pages of comprehensive documentation
- `contracts/docs/` contains NO cross-reference to audit findings

**Problem:** Developers working in `contracts` won't discover lessons learned.

---

## DRY Strategy for Multi-Repo Architecture

### Principle: "Single Source of Truth, Referenced Everywhere"

```
❌ BAD:  Copy-paste script to every repo
✅ GOOD: Template in .github, symlinked/synced to repos

❌ BAD:  Duplicate workflow logic across repos
✅ GOOD: Reusable workflow with repo-specific inputs

❌ BAD:  Duplicate documentation in every repo
✅ GOOD: Centralized docs + cross-repo links
```

---

## Implementation Plan

### Phase 1: Immediate Fixes (Week 1)

#### 1.1 Centralize `check-licenses.sh`

**Action:**

````bash
# Create template directory
mkdir -p .github/templates/scripts/

# Move script to template
cp .github/scripts/check-licenses.sh .github/templates/scripts/check-licenses.sh

# Add sync mechanism
cat > .github/templates/scripts/README.md <<'EOF'
# Shared Scripts

These scripts are templates for use across all SecPal repositories.

## Usage

### check-licenses.sh
Copy to your repo:
```bash
curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh > scripts/check-licenses.sh
chmod +x scripts/check-licenses.sh
````

### Auto-sync

Add to `.github/workflows/sync-templates.yml`:

```yaml
- name: Sync shared scripts
  run: |
    curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh > scripts/check-licenses.sh
```

EOF

````

**Update contracts:**
```bash
cd /home/user/code/SecPal/contracts
curl -s https://raw.githubusercontent.com/SecPal/.github/main/templates/scripts/check-licenses.sh > scripts/check-licenses.sh
````

**Benefit:** Single source of truth. Update once, sync everywhere.

---

#### 1.2 Create Reusable Workflow for License Checking

**Location:** `.github/.github/workflows/reusable-dependency-review.yml`

```yaml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

name: Reusable Dependency Review

on:
  workflow_call:
    inputs:
      skip-dependabot-workflow-only:
        description: "Skip dependency review for Dependabot workflow-only changes"
        required: false
        type: boolean
        default: false

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      # Optional: Dependabot workflow-only skip logic
      - name: Check if GitHub Actions only changes
        if: inputs.skip-dependabot-workflow-only
        id: check-files
        run: |
          files=$(gh pr view ${{ github.event.pull_request.number }} --json files -q '.files[].path')
          all_workflows=true
          while IFS= read -r file; do
            if [[ ! "$file" =~ ^\.github/workflows/ ]]; then
              all_workflows=false
              break
            fi
          done <<< "$files"
          echo "all_workflows=$all_workflows" >> $GITHUB_OUTPUT
        env:
          GH_TOKEN: ${{ github.token }}

      # Shared license policy loading
      - name: Load license policy
        id: policy
        run: |
          if [ ! -f .license-policy.json ]; then
            echo "Error: .license-policy.json not found!" >&2
            exit 1
          fi
          DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)
          if [ -z "$DENIED" ]; then
            echo "Error: deniedLicenses is empty in .license-policy.json!" >&2
            exit 1
          fi
          echo "denied=$DENIED" >> $GITHUB_OUTPUT

      # Shared dependency review
      - name: Dependency Review
        if: |
          !inputs.skip-dependabot-workflow-only ||
          steps.check-files.outputs.all_workflows != 'true' ||
          github.actor != 'dependabot[bot]'
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: moderate
          deny-licenses: ${{ steps.policy.outputs.denied }}
```

**Usage in each repo:**

```yaml
# .github repo: .github/workflows/dependency-review.yml
name: Dependency Review
on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: false

# contracts repo: .github/workflows/dependency-review.yml
name: Dependency Review
on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: true  # Only difference!
```

**Benefit:**

- 95% of logic centralized
- Repo-specific behavior via inputs
- Update once, applies everywhere

---

#### 1.3 Split License Policy into Base + Extensions

**Location:** `.github/config/license-policy-base.json`

```json
{
  "description": "Base license policy for all SecPal repositories",
  "comment": "These licenses are allowed in ALL SecPal projects",
  "allowedLicenses": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "CC0-1.0", "Unlicense"],
  "deniedLicenses": ["GPL-2.0", "LGPL-2.0", "LGPL-2.1", "AGPL-1.0"]
}
```

**Repo-specific extensions:**

```json
// .github/.license-policy.json
{
  "extends": "https://raw.githubusercontent.com/SecPal/.github/main/config/license-policy-base.json",
  "allowedLicensesExtensions": [
    "WTFPL",
    "Python-2.0"
  ],
  "description": ".github repo can use permissive licenses for tooling"
}

// contracts/.license-policy.json
{
  "extends": "https://raw.githubusercontent.com/SecPal/.github/main/config/license-policy-base.json",
  "allowedLicensesExtensions": [
    "GPL-3.0-or-later",
    "LGPL-3.0-or-later",
    "AGPL-3.0-or-later"
  ],
  "description": "contracts repo can use AGPL-compatible licenses"
}
```

**Script to merge:** `scripts/merge-license-policy.sh`

```bash
#!/bin/bash
# Merge base + extension policies

base=$(curl -s https://raw.githubusercontent.com/SecPal/.github/main/config/license-policy-base.json)
extensions=$(jq -r '.allowedLicensesExtensions // [] | .[]' .license-policy.json)

# Combine base + extensions
combined=$(echo "$base" | jq --argjson ext "$(jq -c '.allowedLicensesExtensions // []' .license-policy.json)" '.allowedLicenses += $ext')

echo "$combined"
```

**Benefit:**

- Common policy maintained centrally
- Repo-specific needs documented explicitly
- Changes to base automatically propagate

---

#### 1.4 Add Cross-Repo Documentation Links

**Location:** `contracts/docs/README.md`

```markdown
# Contracts Repository Documentation

## Project-Specific Documentation

- [API Schemas](../openapi/)
- [Testing Guide](./TESTING.md)
- [Contributing](./CONTRIBUTING.md)

## Organization-Wide Documentation

For comprehensive audit findings, lessons learned, and prevention strategies, see:

- **Audit Report:** [.github/docs/AUDIT-REPORT-2025-10-12.md](https://github.com/SecPal/.github/blob/main/docs/AUDIT-REPORT-2025-10-12.md)
- **Prevention Strategy:** [.github/docs/PREVENTION-STRATEGY.md](https://github.com/SecPal/.github/blob/main/docs/PREVENTION-STRATEGY.md)
- **Lessons Learned:** [.github/docs/LESSONS-LEARNED-CONTRACTS-REPO.md](https://github.com/SecPal/.github/blob/main/docs/LESSONS-LEARNED-CONTRACTS-REPO.md)
- **Action Items:** [.github/docs/ACTION-ITEMS.md](https://github.com/SecPal/.github/blob/main/docs/ACTION-ITEMS.md)

> **Note:** Organization-wide documentation is maintained in the `.github` repository to avoid duplication.
```

**Add to all repos:**

- `contracts/README.md` (link section)
- `api/README.md` (when created)
- `frontend/README.md` (when created)

---

#### 1.5 Phase 1b: Copilot Review Workflow Centralization ✅ COMPLETED

**Date:** 2025-10-15
**Status:** DEPLOYED
**PRs:** SecPal/.github#25, SecPal/contracts#22

**Problem:**
Copilot Review Enforcement workflow was 180 lines, duplicated identically in both `.github` and `contracts` repositories. Bug fixes required changes in multiple places, violating DRY.

**Solution:**
Created reusable workflow pattern with `workflow_call` trigger:

**Reusable Workflow:** `.github/.github/workflows/reusable-copilot-review.yml` (180 lines)

- Single source of truth
- Contains all enforcement logic (HEAD verification, low-confidence detection, comment counting)
- Can be called from any SecPal repository

**Caller Workflows:** (20 lines each in both repos)

```yaml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

name: Copilot Review Enforcement

on:
  pull_request:
  pull_request_review:
  pull_request_review_comment:

jobs:
  verify-copilot-review:
    uses: SecPal/.github/.github/workflows/reusable-copilot-review.yml@main
    permissions:
      pull-requests: read
      checks: write
```

**Metrics:**

- **Code reduction:** 180 lines → 20 lines per repo (89% reduction)
- **Files changed:** 2 repos × 1 file = 2 files
- **Lines added:** 180 (reusable) + 40 (callers) = 220 lines
- **Lines removed:** 324 lines (180 × 2 duplicates - 20 × 2 callers)
- **Net change:** -104 lines (32% reduction)
- **Maintenance effort:** 1 file to update instead of 2 (50% reduction)

**Benefits:**

1. **Single Source of Truth:** Bug fixes only need one update
2. **Consistent Behavior:** Same enforcement logic across all repos
3. **Easy Adoption:** New repos need only 20-line caller
4. **Version Control:** Can pin to specific versions if needed (`@v1.0.0`)
5. **Always Latest:** Using `@main` ensures automatic updates propagate

**Design Decision:**
Using `@main` reference instead of pinned versions because:

- Both repos owned by SecPal organization (full control)
- DRY goal requires automatic propagation of updates
- Breaking changes tested in `.github` repo first
- If needed, can switch to versioned tags later

**Security Check Exception:**
Updated `contracts/.github/workflows/security.yml` to allow `@main` for SecPal reusable workflows:

```bash
# Exception: SecPal reusable workflows may use @main (DRY principle)
if grep -r -E "uses:.*@main$|uses:.*@master$" .github/workflows/ 2>/dev/null | grep -v "uses: SecPal/"; then
  echo "External actions must be pinned"
  exit 1
fi
```

**Lessons Learned:**

- Chicken-egg problem: Workflow can't check itself on first deployment (temporarily disable branch protection check)
- SPDX headers must be at file start for consistency
- GraphQL `resolveReviewThread` mutation works for programmatic comment resolution
- Review request via MCP tool (`mcp_github_github_request_copilot_review`) more reliable than `@copilot review` comment

**References:**

- Lesson #18: Copilot Review Enforcement System
- Lesson #19: Infinite Review Loop Prevention
- `README-COPILOT-ENFORCEMENT.md` (both repos)

---

### Phase 2: Automated Synchronization (Week 2-3)

#### 2.1 Template Sync Workflow

**Location:** `.github/workflows/sync-templates.yml`

```yaml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

name: Sync Templates to Repos

on:
  push:
    branches: [main]
    paths:
      - "templates/**"
  workflow_dispatch:
    inputs:
      target_repos:
        description: 'Repos to sync (comma-separated, or "all")'
        required: false
        default: "all"

jobs:
  sync:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        repo: [contracts, api, frontend]
    steps:
      - uses: actions/checkout@v5

      - name: Sync scripts to ${{ matrix.repo }}
        run: |
          echo "📦 Syncing scripts to SecPal/${{ matrix.repo }}..."

          # Clone target repo
          git clone https://github.com/SecPal/${{ matrix.repo }}.git /tmp/${{ matrix.repo }}
          cd /tmp/${{ matrix.repo }}

          # Copy templates
          cp $GITHUB_WORKSPACE/templates/scripts/check-licenses.sh scripts/check-licenses.sh

          # Create PR if changes detected
          if git diff --quiet; then
            echo "✅ No changes needed"
          else
            git checkout -b sync/templates-$(date +%s)
            git add scripts/
            git commit -S -m "chore: sync shared scripts from .github templates"
            git push origin HEAD

            gh pr create \
              --title "chore: Sync shared scripts from .github templates" \
              --body "Automated sync from .github/templates/scripts/" \
              --label "automated,sync"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Benefit:** Changes to templates automatically propagate via PRs

---

#### 2.2 Drift Detection Workflow

**Location:** `.github/workflows/detect-drift.yml`

```yaml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

name: Detect Template Drift

on:
  schedule:
    - cron: "0 8 * * 1" # Every Monday
  workflow_dispatch:

jobs:
  detect-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Check all repos for drift
        run: |
          echo "🔍 Checking for template drift..."

          repos=("contracts" "api" "frontend")
          drift_detected=false

          for repo in "${repos[@]}"; do
            echo "Checking SecPal/$repo..."

            # Get remote script
            remote=$(curl -s "https://raw.githubusercontent.com/SecPal/$repo/main/scripts/check-licenses.sh")
            template=$(cat templates/scripts/check-licenses.sh)

            if [ "$remote" != "$template" ]; then
              echo "❌ Drift detected in $repo!"
              diff <(echo "$template") <(echo "$remote") || true
              drift_detected=true
            else
              echo "✅ $repo is in sync"
            fi
          done

          if [ "$drift_detected" = true ]; then
            echo ""
            echo "⚠️  Template drift detected! Run sync-templates workflow."
            exit 1
          fi
```

---

### Phase 3: Advanced DRY (Month 2+)

#### 3.1 Shared Action for License Policy Loading

**Location:** `.github/actions/load-license-policy/action.yml`

```yaml
name: Load License Policy
description: Loads and validates .license-policy.json with error handling
outputs:
  allowed:
    description: Comma-separated allowed licenses
  denied:
    description: Comma-separated denied licenses
runs:
  using: composite
  steps:
    - name: Validate and load policy
      shell: bash
      run: |
        if [ ! -f .license-policy.json ]; then
          echo "Error: .license-policy.json not found!" >&2
          exit 1
        fi

        ALLOWED=$(jq -r '.allowedLicenses | join(", ")' .license-policy.json)
        DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)

        if [ -z "$DENIED" ]; then
          echo "Error: deniedLicenses is empty!" >&2
          exit 1
        fi

        echo "allowed=$ALLOWED" >> $GITHUB_OUTPUT
        echo "denied=$DENIED" >> $GITHUB_OUTPUT
```

**Usage:**

```yaml
- uses: SecPal/.github/actions/load-license-policy@main
  id: policy

- uses: actions/dependency-review-action@v4
  with:
    deny-licenses: ${{ steps.policy.outputs.denied }}
```

---

#### 3.2 Monorepo-Style Script Management

**Option:** If repos grow to 10+, consider:

```
SecPal/shared-scripts/
├── check-licenses.sh
├── validate-config.sh
├── audit-dependencies.sh
└── version 1.2.3

All repos depend on:
  - shared-scripts@1.2.3
```

Install via:

```bash
npm install @secpal/shared-scripts
npx @secpal/check-licenses
```

---

## DRY Metrics & Success Criteria

| Metric              | Current          | Target (Phase 1)       | Target (Phase 3)   |
| ------------------- | ---------------- | ---------------------- | ------------------ |
| Duplicate Scripts   | 2 copies         | 1 template + sync      | 0 (npm package)    |
| Duplicate Workflows | 2 × 95%          | 2 × 5% (inputs only)   | Reusable workflows |
| Duplicate Docs      | Full duplication | Cross-links            | Central wiki       |
| Sync Time           | Manual (hours)   | Automated PR (minutes) | Real-time (CI/CD)  |
| Drift Detection     | Manual audit     | Weekly automated       | Pre-commit hook    |

---

## Guidelines for Future Development

### When Adding New Scripts

**❌ DON'T:**

```bash
# Copy script to new repo
cp contracts/scripts/new-tool.sh api/scripts/new-tool.sh
```

**✅ DO:**

```bash
# Add to templates first
echo "script" > .github/templates/scripts/new-tool.sh

# Sync to all repos
.github/workflows/sync-templates.yml
```

---

### When Adding New Workflows

**❌ DON'T:**

```yaml
# Copy entire workflow
cp .github/workflows/security.yml contracts/.github/workflows/security.yml
```

**✅ DO:**

```yaml
# Create reusable workflow
# .github/.github/workflows/reusable-security.yml
name: Reusable Security Scan
on: workflow_call

# Use in each repo
jobs:
  security:
    uses: SecPal/.github/.github/workflows/reusable-security.yml@main
```

---

### When Documenting Lessons

**❌ DON'T:**

```markdown
# Copy LESSONS-LEARNED.md to every repo
```

**✅ DO:**

```markdown
# Add cross-link in repo README

See [Organization-Wide Lessons](.github/docs/LESSONS-LEARNED.md)
```

---

## Breaking Changes & Migration

### If Template Changes Are Breaking

1. **Version the template:**

   ```
   templates/scripts/check-licenses.v1.sh
   templates/scripts/check-licenses.v2.sh
   ```

2. **Gradual migration:**

   ```bash
   # Repo 1: Test v2
   # Repo 2-5: Stay on v1
   # After 2 weeks: Migrate all
   ```

3. **Communication:**
   - Create migration guide
   - Announce in GitHub Discussions
   - Create tracking issue

---

## Related Documents

- **Audit Report:** `AUDIT-REPORT-2025-10-12.md` (DRY violations documented)
- **Prevention Strategy:** `PREVENTION-STRATEGY.md` (Phase 1 includes templates)
- **Action Items:** `ACTION-ITEMS.md` (DRY fixes prioritized)

---

## Summary

**Problem:** Significant code duplication across repos (100% identical scripts, 95% identical workflows)

**Impact:**

- 2× maintenance effort
- 2× risk of bugs
- Inconsistent updates
- Wasted developer time

**Solution:**

- Phase 1: Templates + reusable workflows (Week 1)
- Phase 2: Automated sync + drift detection (Week 2-3)
- Phase 3: Shared packages + advanced automation (Month 2+)

**Next Steps:**

1. Review this strategy
2. Approve centralization approach
3. Begin Phase 1 implementation
4. Update both open PRs with template references

---

**Document Version:** 1.1
**Status:** IN PROGRESS - Phase 1b Complete
**Last Updated:** 2025-10-15
**Estimated Implementation:** 2-3 weeks (Phase 1), 2 months (full)

---

## Implementation Status

### ✅ Completed

- **Phase 1b (2025-10-15):** Copilot Review Workflow centralization
  - Reusable workflow created and deployed
  - Both repos migrated (89% code reduction)
  - Security exceptions documented
  - Branch protection updated

### 🔄 In Progress

- Phase 1: Scripts and license policy centralization
- Phase 2: Automated sync workflows

### ⏳ Planned

- Phase 3: Shared packages and advanced automation
