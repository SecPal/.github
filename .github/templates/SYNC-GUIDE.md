<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Template Sync Guide

**How to Synchronize Templates from `.github` to Other SecPal Repositories**

This guide explains how to keep scripts and workflows synchronized across all SecPal repositories using the centralized templates.

---

## Quick Start

### Sync Scripts to Your Repo

```bash
cd /path/to/your-repo

# Create scripts directory if it doesn't exist
mkdir -p scripts

# Sync all shared scripts
for script in check-licenses.sh pre-work-check.sh post-commit-check.sh; do
  curl -o scripts/$script \
    https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/$script
  chmod +x scripts/$script
done

echo "✅ Scripts synchronized!"
```

### Migrate to Reusable Workflows

```bash
cd /path/to/your-repo

# Example: Replace dependency-review.yml with reusable workflow call
cat > .github/workflows/dependency-review.yml <<'EOF'
name: Dependency Review

on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: false  # Change to true if needed
EOF

git add .github/workflows/dependency-review.yml
git commit -m "refactor: use reusable dependency-review workflow"
git push
```

---

## Synchronization Methods

### Method 1: Manual Sync (Quick & Easy)

**When to use:**

- One-time setup
- Testing new templates
- Hotfixes

**Steps:**

1. **Sync Scripts:**

   ```bash
   curl -o scripts/check-licenses.sh \
     https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/check-licenses.sh
   chmod +x scripts/check-licenses.sh
   ```

2. **Test Locally:**

   ```bash
   ./scripts/check-licenses.sh
   ```

3. **Commit & Push:**
   ```bash
   git add scripts/
   git commit -m "chore: sync scripts from .github templates"
   git push
   ```

---

### Method 2: Automated Weekly Sync (Recommended)

**When to use:**

- Production repositories
- Long-term maintenance
- Multiple repos

**Setup:**

Create `.github/workflows/sync-scripts.yml`:

```yaml
name: Sync Scripts

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sundays at midnight
  workflow_dispatch:      # Allow manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v5
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Sync shared scripts
        run: |
          echo "📦 Syncing scripts from .github templates..."

          for script in check-licenses.sh pre-work-check.sh post-commit-check.sh; do
            echo "  - $script"
            curl -s -o scripts/$script \
              https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/$script
            chmod +x scripts/$script
          done

          echo "✅ Scripts synchronized"

      - name: Check for changes
        id: check
        run: |
          if git diff --quiet scripts/; then
            echo "has_changes=false" >> $GITHUB_OUTPUT
            echo "✅ No changes needed - scripts are up to date"
          else
            echo "has_changes=true" >> $GITHUB_OUTPUT
            echo "📝 Changes detected:"
            git diff --name-only scripts/
          fi

      - name: Create Pull Request
        if: steps.check.outputs.has_changes == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          branch="sync/scripts-$(date +%s)"
          git checkout -b "$branch"
          git add scripts/

          # Use heredoc for multi-line commit message to avoid shell parsing issues
          git commit -F- <<EOF
          chore: sync shared scripts from .github templates

          Automated sync from SecPal/.github templates.

          Scripts updated:
          $(git diff --name-only HEAD~1 scripts/ | sed 's/^/- /')

          Source: https://github.com/SecPal/.github/tree/main/.github/templates/scripts
          EOF

          git push origin "$branch"

          gh pr create \
            --title "chore: Sync shared scripts from .github templates" \
            --body "**Automated sync from .github templates**

## Changes

$(git diff --stat HEAD~1 scripts/)

## Scripts Updated

$(git diff --name-only HEAD~1 scripts/ | sed 's/^/- /')

## Source

https://github.com/SecPal/.github/tree/main/.github/templates/scripts

## Testing

Scripts are tested in the .github repository before being promoted to templates. This PR ensures your repository uses the latest versions.

## Checklist

- [x] Scripts synced from templates
- [x] Executable permissions set
- [ ] CI checks passing (automated)
- [ ] Manual testing (if needed)" \
            --label "dependencies" \
            --label "automation"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Benefits:**

- ✅ Automatic updates every week
- ✅ Creates PR for review (not direct merge)
- ✅ Shows what changed
- ✅ CI runs before merge
- ✅ Can be manually triggered anytime

---

### Method 3: On-Demand Sync Script

**When to use:**

- Developer workflow
- Testing before committing
- Manual control

**Create `scripts/sync-from-templates.sh`:**

```bash
#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

TEMPLATE_BASE="https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts"
SCRIPTS=(
  "check-licenses.sh"
  "pre-work-check.sh"
  "post-commit-check.sh"
)

echo "📦 Syncing scripts from .github templates..."
echo

for script in "${SCRIPTS[@]}"; do
  echo "  Downloading $script..."
  if curl -sf -o "scripts/$script" "$TEMPLATE_BASE/$script"; then
    chmod +x "scripts/$script"
    echo "  ✅ $script synced"
  else
    echo "  ❌ Failed to download $script" >&2
    exit 1
  fi
done

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All scripts synchronized!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "Next steps:"
echo "  1. Test scripts: ./scripts/check-licenses.sh"
echo "  2. Review changes: git diff scripts/"
echo "  3. Commit: git add scripts/ && git commit -m 'chore: sync scripts'"
```

**Usage:**

```bash
chmod +x scripts/sync-from-templates.sh
./scripts/sync-from-templates.sh
```

---

## Workflow Migration Guide

### Step 1: Identify Workflows to Migrate

**Candidates:**

- `dependency-review.yml` → `reusable-dependency-review.yml`
- Custom license checks → `reusable-license-check.yml`
- Any workflow with shared logic across repos

### Step 2: Compare with Reusable Workflow

**Check:** Does the reusable workflow cover your use case?

```bash
# View reusable workflow
curl -s https://raw.githubusercontent.com/SecPal/.github/main/.github/workflows/reusable-dependency-review.yml
```

### Step 3: Replace with Workflow Call

**Before (56 lines):**

```yaml
name: Dependency Review
on:
  pull_request:
    branches: [main]

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Load license policy
        id: policy
        run: |
          # ... 15 lines of bash ...
      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          deny-licenses: ${{ steps.policy.outputs.denied }}
```

**After (10 lines):**

```yaml
name: Dependency Review
on:
  pull_request:
    branches: [main]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: false
```

**Savings:** 82% less code! ✨

### Step 4: Test & Verify

1. **Create PR** with migrated workflow
2. **Verify CI passes** with reusable workflow
3. **Check logs** to ensure behavior unchanged
4. **Merge** when confident

---

## Troubleshooting

### Script Not Found After Sync

**Error:**

```
❌ Error: scripts/check-licenses.sh not found or not executable!
```

**Fix:**

```bash
# Re-sync script
curl -o scripts/check-licenses.sh \
  https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/check-licenses.sh
chmod +x scripts/check-licenses.sh

# Verify
ls -lah scripts/check-licenses.sh
```

### Workflow Not Found

**Error:**

```
Error: Unable to resolve action SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
```

**Causes:**

1. Workflow not yet merged to main in `.github` repo
2. Path typo (should be `.github/workflows/reusable-*.yml`)
3. Private repo without proper access

**Fix:**

```bash
# Check if workflow exists
curl -I https://raw.githubusercontent.com/SecPal/.github/main/.github/workflows/reusable-dependency-review.yml

# Verify path in calling workflow
cat .github/workflows/dependency-review.yml
```

### Sync Creates Too Many PRs

**Problem:** Weekly sync creates PR even for trivial changes

**Solution:** Add change threshold to workflow:

```yaml
- name: Check for significant changes
  id: check
  run: |
    lines_changed=$(git diff --numstat scripts/ | awk '{sum+=$1+$2} END {print sum}')
    if [ "$lines_changed" -lt 5 ]; then
      echo "has_changes=false" >> $GITHUB_OUTPUT
      echo "⚠️  Only $lines_changed lines changed - skipping PR"
    else
      echo "has_changes=true" >> $GITHUB_OUTPUT
    fi
```

---

## Best Practices

### ✅ DO

- **Test locally** before syncing to production
- **Review PRs** from automated syncs
- **Keep templates stable** - test in `.github` first
- **Document repo-specific changes** in commit messages
- **Use semantic versioning** when possible (`@v1.0.0`)

### ❌ DON'T

- **Don't modify synced scripts** in consuming repos (changes will be overwritten)
- **Don't sync blindly** - review what changed
- **Don't skip testing** after sync
- **Don't use `@main` in production** without understanding risks

---

## Related Documentation

- **Scripts Templates:** [scripts/README.md](scripts/README.md)
- **Workflows Templates:** [workflows/README.md](workflows/README.md)
- **DRY Strategy:** [../../docs/DRY-ANALYSIS-AND-STRATEGY.md](../../docs/DRY-ANALYSIS-AND-STRATEGY.md)

---

**Last Updated:** 2025-10-14
**Maintained by:** SecPal Contributors
