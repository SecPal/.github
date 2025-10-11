# Lessons Learned: contracts Repository Setup

**Date:** 2025-10-11
**Repository:** SecPal/contracts
**Purpose:** OpenAPI specifications and TypeScript type definitions

## Summary

This document captures all issues encountered and solutions implemented during the setup of the `contracts` repository. These lessons should be applied to future SecPal repositories to avoid repeating the same problems.

---

## 🔴 Critical Issues Fixed

### 1. Branch Protection: Wrong Status Check Context Names

**Problem:**

- Branch protection was configured with `"Workflow Name / Job Name"` format
- Example: `"Tests / contracts-tests"`, `"Code Formatting / prettier"`
- GitHub uses only the **job name** as the context: `contracts-tests`, `prettier`
- Result: Branch protection never saw the checks, PRs couldn't be merged

**Solution:**

```json
{
  "required_status_checks": {
    "contexts": [
      "contracts-tests", // ✅ Correct: just the job name
      "prettier", // ✅ Not "Code Formatting / prettier"
      "reuse",
      "check-npm-licenses",
      "verify-commits"
    ]
  }
}
```

**Action for Future Repos:**

- Always use `gh pr view <PR> --json statusCheckRollup --jq '.statusCheckRollup[].name'` to get actual check names
- Update branch-protection templates in .github repo

---

### 2. Signed Commits: `git verify-commit` Doesn't Work in GitHub Actions

**Problem:**

- Workflow used `git verify-commit $commit` to verify GPG signatures
- GPG public keys are not available in Actions checkout
- All signed commits failed verification in CI

**Solution:**
Use GitHub API instead:

```yaml
- name: Verify all commits are signed
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    commits=$(gh api repos/${{ github.repository }}/pulls/${{ github.event.pull_request.number }}/commits --jq '.[].sha')

    for commit in $commits; do
      verified=$(gh api repos/${{ github.repository }}/commits/$commit --jq '.commit.verification.verified')
      if [[ "$verified" != "true" ]]; then
        echo "❌ Commit $commit is not signed!"
        exit 1
      fi
    done
```

**Action for Future Repos:**

- Update `signed-commits.yml` workflow template with GitHub API approach
- Remove `git verify-commit` usage

---

### 3. Dependency Review: Invalid "proprietary" License Identifier

**Problem:**

- Workflow had `deny-licenses: GPL-2.0, LGPL-2.0, LGPL-2.1, AGPL-1.0, proprietary`
- `proprietary` is not a valid SPDX license identifier
- Action failed with: `##[error]Invalid license(s) in deny-licenses: proprietary`

**Solution:**

```yaml
- uses: actions/dependency-review-action@v4
  with:
    fail-on-severity: moderate
    deny-licenses: GPL-2.0, LGPL-2.0, LGPL-2.1, AGPL-1.0 # Removed proprietary
```

**Action for Future Repos:**

- Update `dependency-review.yml` template
- Only use valid SPDX identifiers

---

### 4. Dependabot PRs Failed Signed Commits Check

**Problem:**

- Dependabot commits are not GPG-signed (bot commits)
- Workflow failed all Dependabot PRs

**Solution:**

```yaml
- name: Verify all commits are signed
  run: |
    # Skip verification for Dependabot PRs
    if [[ "${{ github.actor }}" == "dependabot[bot]" ]]; then
      echo "✅ Skipping signature verification for Dependabot"
      exit 0
    fi

    # ... rest of verification
```

**Action for Future Repos:**

- Add Dependabot skip logic to signed-commits workflow template

---

### 5. Dependabot PRs Failed Dependency Review (GitHub Actions Updates)

**Problem:**

- Dependabot PRs updating only `.github/workflows/` files triggered dependency-review
- Review failed because actions aren't "npm dependencies"

**Solution:**

```yaml
- name: Check if GitHub Actions only changes
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

- name: Dependency Review
  if: steps.check-files.outputs.all_workflows != 'true' || github.actor != 'dependabot[bot]'
  uses: actions/dependency-review-action@v4
```

**Action for Future Repos:**

- Update dependency-review.yml template with skip logic

---

### 6. Branch Protection: Admin Bypass Enabled

**Problem:**

- `enforce_admins: false` allowed repository admins to bypass all branch protection rules
- Defeats the purpose of having branch protection for a solo maintainer

**Solution:**

```json
{
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0, // Solo maintainer can merge own PRs
    "dismiss_stale_reviews": true
  }
}
```

**Action for Future Repos:**

- Set `enforce_admins: true` in branch protection templates
- Set review count to 0 for solo maintainer workflows

---

## ⚠️ Issues to Be Aware Of

### 7. package-lock.json Must Be Committed (npm Projects)

**Problem:**

- `package-lock.json` was in `.gitignore`
- CI used `npm ci` which requires exact lockfile
- Workflow failed: `npm ci can only install packages when your package.json and package-lock.json are in sync`

**Solution:**

- Remove `package-lock.json` from `.gitignore`
- Commit the lockfile
- Use `npm ci` in CI/CD (faster, more reliable than `npm install`)

**Action for Future Repos (npm/Node.js):**

- Never ignore `package-lock.json`, `yarn.lock`, or `pnpm-lock.yaml`
- Add note to repo setup checklist

---

### 8. REUSE.toml Itself Needs SPDX Headers

**Problem:**

- REUSE compliance check failed: "22 / 23 files compliant"
- The missing file was `REUSE.toml` itself!
- REUSE configuration file needs its own headers

**Solution:**

```toml
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

version = 1
SPDX-PackageName = "SecPal Contracts"
# ... rest of config
```

**Action for Future Repos:**

- Add SPDX headers to REUSE.toml template
- Add this to REUSE compliance checklist

---

### 9. Deprecated Dependencies (Jest's glob@7.2.3)

**Problem:**

- `npm ci` showed warnings:
  - `npm warn deprecated inflight@1.0.6: This module is not supported, and leaks memory`
  - `npm warn deprecated glob@7.2.3: Glob versions prior to v9 are no longer supported`
- These are **transitive dependencies** from Jest 29.7.0
- Updated `@redocly/cli` 1.x → 2.x which fixed their glob usage
- Jest issue remains (waiting for Jest team to update)

**Solution:**

- Update direct dependencies where possible
- Accept transitive dependency warnings for now (no security issues)
- Consider alternative testing frameworks if deprecated warnings become problematic

**Action for Future Repos:**

- Check for deprecated dependencies during setup
- Update to latest major versions where feasible
- Document known deprecated transitive dependencies

---

### 10. Dependency Graph Requires Explicit Activation

**Problem:**

- `dependency-review-action` failed: "Dependency review is not supported on this repository"
- Even though repo is public, Dependency Graph was not activated
- Cannot be activated via API alone

**Solution:**

- Enable via GitHub Settings → Security → Dependency graph
- Or via API: `gh api -X PATCH repos/SecPal/contracts -f has_vulnerability_alerts=true`
- Note: May still require manual web UI activation

**Action for Future Repos:**

- Add "Enable Dependency Graph" to repository setup checklist
- Include link: `https://github.com/SecPal/<repo>/settings/security_analysis`

---

## 📋 Checklist for Future Repositories

### Initial Setup

- [ ] Create repository with correct description and license
- [ ] Clone locally
- [ ] Set up project structure (tech-specific)
- [ ] Add LICENSE file (AGPL-3.0-or-later)
- [ ] Create REUSE.toml **with SPDX headers**
- [ ] Add LICENSES/AGPL-3.0-or-later.txt

### Workflows Setup

- [ ] Copy workflows from .github repo (use **corrected** versions)
- [ ] Update workflow files for project tech stack
- [ ] Verify job names match what branch protection expects
- [ ] Test workflows with initial commit

### Dependency Management

- [ ] For npm: Ensure package-lock.json is **not** in .gitignore
- [ ] For Python: Commit requirements.txt or poetry.lock
- [ ] For other: Commit respective lock files
- [ ] Run `npm audit` / equivalent security check
- [ ] Update deprecated dependencies

### Branch Protection

- [ ] Create branch-protection-main.json with:
  - `enforce_admins: true`
  - `required_pull_request_reviews` with count 0
  - **Correct status check context names** (test with a PR first!)
- [ ] Apply branch protection via API
- [ ] Test with a PR to verify all checks are recognized

### GitHub Settings (Manual)

- [ ] Enable Dependency Graph
- [ ] Enable Dependabot alerts
- [ ] Enable secret scanning (if available)
- [ ] Configure Dependabot.yml for weekly updates

### Testing

- [ ] Create test PR to verify:
  - All required checks run and pass
  - Signed commits are verified correctly
  - Dependabot skip logic works
  - Branch protection blocks merge until checks pass
- [ ] Test Dependabot PR (wait for first automated PR or create manual test)

---

## 🔧 Files to Update in .github Repository

### 1. `workflow-templates/signed-commits.yml`

- Replace `git verify-commit` with GitHub API approach
- Add Dependabot skip logic
- Update to use GH_TOKEN environment variable

### 2. `workflow-templates/dependency-review.yml`

- Remove `proprietary` from deny-licenses
- Add GitHub Actions-only file check
- Add Dependabot skip logic

### 3. `workflow-templates/reuse.yml`

- Ensure uses `fsfe/reuse-action@v6` (current latest)
- Document that REUSE.toml needs SPDX headers

### 4. `branch-protection-templates/`

Create separate templates for:

- `node-ts-repo.json` (TypeScript/Node.js projects)
- `python-repo.json` (Python projects)
- `general-repo.json` (Language-agnostic)

Each with:

- `enforce_admins: true`
- Correct context names for that project type
- Review count 0 for solo maintainer

### 5. `docs/REPOSITORY-SETUP-GUIDE.md`

New comprehensive guide covering:

- Step-by-step repo creation
- Workflow setup and customization
- Branch protection configuration
- Testing and validation
- All lessons learned from this document

### 6. `docs/WORKFLOW-STATUS-CHECK-NAMES.md`

Document how to find correct status check names:

```bash
# For an existing PR
gh pr view <PR> --json statusCheckRollup --jq '.statusCheckRollup[].name'

# This gives you the EXACT names to use in branch protection
```

---

## 🎯 Next Repositories

### API Repository (Python/FastAPI expected)

**Additional Considerations:**

- Use `poetry.lock` or `requirements.txt` (commit it!)
- Python-specific workflows (pytest, black, mypy, ruff)
- Status check names will be different
- May need `pyproject.toml` SPDX headers
- Consider `pip-audit` for security scanning

### Frontend Repository (React/TypeScript expected)

**Additional Considerations:**

- Similar to contracts repo (TypeScript)
- Will have `package-lock.json` issues (same fix)
- May use Vite or Next.js (different build commands)
- ESLint/Prettier configuration
- Bundle size checks
- E2E testing (Playwright/Cypress)

---

## 📊 Metrics

### Time Investment

- Initial setup: ~1 hour
- Debugging and fixes: ~3 hours
- Total: ~4 hours for first repository

### Expected Time for Next Repos

- With corrected templates: ~30 minutes
- Testing and validation: ~30 minutes
- **Total: ~1 hour per repository**

### ROI

- 75% time savings on subsequent repos
- Consistent quality and security across all repos
- Automated checks prevent issues early
- Clear documentation for future contributors

---

## ✅ Success Criteria Met

- [x] Branch protection active and enforced (including for admins)
- [x] All 5 required status checks passing
- [x] Signed commits verified correctly
- [x] Dependabot PRs work without manual intervention
- [x] REUSE compliance (22/22 files)
- [x] No security vulnerabilities
- [x] Deprecated dependencies documented and updated where possible
- [x] PR-based workflow established
- [x] All checks run locally before push

---

## 🔄 Continuous Improvement

### Monitoring

- Review Dependabot PRs weekly
- Check for new deprecated dependencies monthly
- Update workflows when GitHub Actions get new features
- Review branch protection effectiveness quarterly

### Iteration

- Update templates as we learn from API and Frontend repos
- Add language-specific best practices
- Create automation scripts where possible
- Keep this document updated

---

**Document Version:** 1.0
**Last Updated:** 2025-10-11
**Author:** GitHub Copilot (AI Assistant) with human guidance
