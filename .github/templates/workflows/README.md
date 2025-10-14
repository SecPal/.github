<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Reusable Workflow Templates

**Single Source of Truth for GitHub Actions Workflows Across All SecPal Repositories**

These reusable workflows eliminate 95% code duplication across SecPal repos while allowing repo-specific customization via inputs.

---

## Available Workflows

### 1. `reusable-dependency-review.yml`

**Purpose:** Centralized dependency review with license policy enforcement

**Usage in your repo:**

```yaml
# .github/workflows/dependency-review.yml
name: Dependency Review

on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: true # Set to false if not needed
```

**Inputs:**

| Input                           | Type    | Required | Default | Description                                      |
| ------------------------------- | ------- | -------- | ------- | ------------------------------------------------ |
| `skip-dependabot-workflow-only` | boolean | No       | `false` | Skip review if Dependabot only changes workflows |

**What it does:**

- ✅ Loads `.license-policy.json` with validation
- ✅ Runs `actions/dependency-review-action@v4`
- ✅ Optional: Skips Dependabot workflow-only PRs (contracts repo uses this)
- ✅ Fails on moderate+ severity or denied licenses

**Requirements:**

- `.license-policy.json` must exist in repo root
- Must have `deniedLicenses` array defined

---

### 2. `reusable-license-check.yml`

**Purpose:** Run `check-licenses.sh` script consistently across all repos

**Usage in your repo:**

```yaml
# .github/workflows/license-check.yml
name: License Compatibility Check

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  check-licenses:
    uses: SecPal/.github/.github/workflows/reusable-license-check.yml@main
```

**No inputs required** - fully automated!

**What it does:**

- ✅ Installs Node.js 20 and npm dependencies
- ✅ Installs `jq` if not present
- ✅ Runs `scripts/check-licenses.sh`
- ✅ Provides helpful error if script missing

**Requirements:**

- `scripts/check-licenses.sh` must exist (sync from templates)
- `.license-policy.json` must exist in repo root

---

## Benefits

✅ **95% Less Duplication:** Core logic centralized, only repo-specific config in each repo
✅ **Consistent Behavior:** All repos use identical CI logic
✅ **Easier Updates:** Fix/improve once, applies everywhere
✅ **Repo-Specific Flexibility:** Inputs allow customization where needed
✅ **Self-Documenting:** Reusable workflows include error messages with fix instructions

---

## Example: Migrating Existing Workflow

### Before (Duplicated in every repo):

```yaml
# .github/workflows/dependency-review.yml (95% duplicate across repos)
name: Dependency Review
on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Load license policy
        id: policy
        run: |
          if [ ! -f .license-policy.json ]; then
            echo "Error: .license-policy.json not found!" >&2
            exit 1
          fi
          DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)
          echo "denied=$DENIED" >> $GITHUB_OUTPUT

      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          deny-licenses: ${{ steps.policy.outputs.denied }}
```

### After (5% repo-specific config):

```yaml
# .github/workflows/dependency-review.yml (repo-specific)
name: Dependency Review
on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
    with:
      skip-dependabot-workflow-only: false # Only difference between repos!
```

**Result:** 95% of code eliminated, maintained centrally! 🎯

---

## Versioning

### Using Latest Version (Recommended for Development)

```yaml
uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@main
```

**Pros:** Automatic updates
**Cons:** Breaking changes possible

### Using Specific Commit (Recommended for Production)

```yaml
uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@3a235c3
```

**Pros:** Stability, reproducible builds
**Cons:** Manual updates required

### Using Release Tag (Recommended when available)

```yaml
uses: SecPal/.github/.github/workflows/reusable-dependency-review.yml@v1.0.0
```

**Pros:** Best of both worlds (semantic versioning)
**Cons:** Requires release management

---

## Creating New Reusable Workflows

### Checklist:

1. **Test in `.github` repo first** - Ensure it works standalone
2. **Identify common logic** - What's duplicated across repos?
3. **Define inputs** - What needs to be repo-specific?
4. **Add error handling** - Helpful messages if requirements missing
5. **Document usage** - Add to this README
6. **Update consumers** - Create PRs to migrate existing workflows
7. **Test in consuming repos** - Verify it works as expected

### Template Structure:

```yaml
name: Reusable Workflow Name

on:
  workflow_call:
    inputs:
      your-input:
        description: "Description of input"
        required: false
        type: boolean
        default: false

jobs:
  your-job:
    runs-on: ubuntu-latest
    steps:
      - name: Your step
        run: echo "Implementation"
```

---

## Related Documentation

- **DRY Strategy:** [../../docs/DRY-ANALYSIS-AND-STRATEGY.md](../../docs/DRY-ANALYSIS-AND-STRATEGY.md)
- **Scripts Templates:** [../scripts/README.md](../scripts/README.md)
- **Repository Setup:** [../../docs/REPOSITORY-SETUP-GUIDE.md](../../docs/REPOSITORY-SETUP-GUIDE.md)

---

## References

- [GitHub Docs: Reusing workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [GitHub Docs: workflow_call event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_call)

---

**Last Updated:** 2025-10-14
**Maintained by:** SecPal Contributors
