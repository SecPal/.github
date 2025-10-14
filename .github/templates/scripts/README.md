<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Shared Script Templates

**Single Source of Truth for Scripts Across All SecPal Repositories**

These templates are maintained centrally in the `.github` repository and synchronized to all SecPal repos. This eliminates code duplication and ensures consistency.

---

## Available Templates

### 1. `check-licenses.sh`

**Purpose:** Validates npm dependencies against `.license-policy.json`

**Usage:**

```bash
# Copy to your repository
curl -o scripts/check-licenses.sh https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/check-licenses.sh
chmod +x scripts/check-licenses.sh

# Test locally
./scripts/check-licenses.sh
```

**Requirements:**

- `jq` installed (`apt-get install jq` or `brew install jq`)
- `.license-policy.json` in repo root

**Used by:**

- `.github` repository
- `contracts` repository
- All future SecPal repositories

---

### 2. `pre-work-check.sh`

**Purpose:** Prevents merge conflicts by ensuring main branch is up-to-date before creating feature branches

**Usage:**

```bash
# Copy to your repository
curl -o scripts/pre-work-check.sh https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/pre-work-check.sh
chmod +x scripts/pre-work-check.sh

# Run before creating feature branch
./scripts/pre-work-check.sh
git checkout -b feature/your-feature
```

**Prevents:**

- Merge conflicts from stale branches (Lesson from PR #19)
- Working on outdated code

**Used by:**

- `.github` repository
- `contracts` repository

---

### 3. `post-commit-check.sh`

**Purpose:** Verifies clean working directory after commits (Lesson #17 enforcement)

**Usage:**

```bash
# Copy to your repository
curl -o scripts/post-commit-check.sh https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/post-commit-check.sh
chmod +x scripts/post-commit-check.sh

# Run after every commit
git commit -m "your message"
./scripts/post-commit-check.sh
```

**Checks:**

- ✅ No uncommitted changes
- ✅ No untracked files (catches temp files like `pr-body-fixed.md`)
- ✅ No unstaged changes (catches formatter-induced modifications)
- ✅ Branch sync status

**Used by:**

- `.github` repository
- `contracts` repository

---

## Synchronization

### Manual Sync

To update scripts in your repository:

```bash
cd /path/to/your-repo

# Update all scripts
for script in check-licenses.sh pre-work-check.sh post-commit-check.sh; do
  curl -o scripts/$script https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/$script
  chmod +x scripts/$script
done

echo "✅ Scripts synchronized"
```

### Automated Sync (Recommended)

Add a GitHub Actions workflow to automatically sync scripts:

```yaml
# .github/workflows/sync-scripts.yml
name: Sync Scripts

on:
  schedule:
    - cron: "0 0 * * 0" # Weekly on Sundays
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Sync shared scripts
        run: |
          for script in check-licenses.sh pre-work-check.sh post-commit-check.sh; do
            curl -o scripts/$script https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/scripts/$script
            chmod +x scripts/$script
          done

      - name: Create PR if changes
        run: |
          if git diff --quiet; then
            echo "No changes needed"
          else
            git checkout -b sync/scripts-$(date +%s)
            git add scripts/
            git commit -S -m "chore: sync shared scripts from .github templates"
            git push origin HEAD
            gh pr create --title "chore: Sync shared scripts" --body "Automated sync from .github templates"
          fi
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Maintenance

### Updating Templates

**Location:** `.github/.github/templates/scripts/`

1. Update script in templates directory
2. Test in `.github` repo first
3. Commit and push to main
4. Scripts will auto-sync to other repos (if automated sync is enabled)
5. Or manually sync using commands above

### Adding New Scripts

1. Create script in `.github/scripts/` first
2. Test thoroughly
3. Copy to `.github/templates/scripts/`
4. Update this README
5. Add to sync workflow (if using automated sync)
6. Document in `REPOSITORY-SETUP-GUIDE.md`

---

## Benefits of Centralized Templates

✅ **Single Source of Truth:** Update once, sync everywhere
✅ **Consistency:** All repos use identical scripts
✅ **Easier Maintenance:** Bug fixes applied to all repos automatically
✅ **Version Control:** Track script changes centrally
✅ **Onboarding:** New repos get latest scripts immediately

---

## Related Documentation

- **DRY Strategy:** [docs/DRY-ANALYSIS-AND-STRATEGY.md](../../docs/DRY-ANALYSIS-AND-STRATEGY.md)
- **Repository Setup:** [docs/REPOSITORY-SETUP-GUIDE.md](../../docs/REPOSITORY-SETUP-GUIDE.md)
- **Lessons Learned:** [docs/LESSONS-LEARNED-CONTRACTS-REPO.md](../../docs/LESSONS-LEARNED-CONTRACTS-REPO.md)

---

**Last Updated:** 2025-10-14
**Maintained by:** SecPal Contributors
