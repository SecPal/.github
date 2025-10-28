<!-- SPDX-FileCopyrightText: 2025 SecPal -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Rollout Guide: Project Automation Workflow

Guide for deploying the project automation workflow to other repositories (api, frontend, contracts).

## 📋 Prerequisites

Before rolling out to a repository:

- [ ] Repository is part of the SecPal organization
- [ ] Repository has issues enabled
- [ ] You have admin access to the repository
- [ ] `PROJECT_TOKEN` secret is set (can be organization-level or repo-level)

## 🚀 Deployment Steps

### Step 1: Create Workflow File

Create `.github/workflows/project-automation.yml` in the target repository:

```yaml
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: CC0-1.0

name: Project Board Automation

on:
  issues:
    types:
      - opened
      - reopened
      - closed
  pull_request:
    types:
      - opened
      - ready_for_review
      - closed
      - converted_to_draft
  pull_request_review:
    types:
      - submitted

jobs:
  automate:
    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main
    secrets:
      PROJECT_TOKEN: ${{ secrets.PROJECT_TOKEN }}
```

That's it! Only ~30 lines needed per repository.

### Step 2: Configure Secret

#### Option A: Organization-Level Secret (Recommended)

Set once for all repositories:

1. Go to Organization Settings → Secrets → Actions
2. Click "New organization secret"
3. Name: `PROJECT_TOKEN`
4. Value: Your fine-grained PAT
5. Repository access: "All repositories" or "Selected repositories"

#### Option B: Repository-Level Secret

Set individually per repository:

```bash
# For api repository
gh secret set PROJECT_TOKEN --repo SecPal/api
# Paste your PAT when prompted

# For frontend repository
gh secret set PROJECT_TOKEN --repo SecPal/frontend

# For contracts repository
gh secret set PROJECT_TOKEN --repo SecPal/contracts
```

### Step 3: Create Required Labels

Create these labels in each repository (or adjust workflow logic):

```bash
# Navigate to repository
cd /path/to/repo

# Create labels
gh label create "enhancement" --color "a2eeef" --description "New feature or request"
gh label create "core-feature" --color "0e8a16" --description "Core functionality - planned implementation"
gh label create "priority: blocker" --color "d93f0b" --description "High priority issue blocking progress"
```

Or via GitHub UI:

1. Go to repository → Issues → Labels
2. Create:
   - `enhancement` (light blue)
   - `core-feature` (dark green)
   - `priority: blocker` (dark red)

### Step 4: Test the Workflow

Create a test issue to verify automation:

```bash
gh issue create \
  --repo SecPal/api \
  --title "Test: Project Automation" \
  --label "enhancement" \
  --body "Testing automatic project board integration.

Expected: Should be added to SecPal Roadmap with status 💡 Ideas"
```

**Verify:**

1. Go to [SecPal Roadmap](https://github.com/orgs/SecPal/projects/1)
2. Check that issue appears with status "💡 Ideas"
3. Check Actions tab for workflow run
4. Issue should have a comment explaining status

### Step 5: Test Draft PR Workflow

```bash
# Create test issue
ISSUE=$(gh issue create \
  --repo SecPal/api \
  --title "Test: Draft PR Workflow" \
  --label "enhancement" \
  --body "Testing draft PR status updates" \
  --json number -q .number)

# Create branch and draft PR
git checkout -b test-automation
echo "test" >> test.txt
git add test.txt
git commit -m "test: Automation"
git push -u origin test-automation

gh pr create \
  --repo SecPal/api \
  --draft \
  --title "WIP: Test automation" \
  --body "Closes #$ISSUE"
```

**Verify:**

1. Issue status should be "🚧 In Progress"
2. Workflow ran successfully (Actions tab)
3. Mark PR ready: `gh pr ready <PR-number>`
4. Issue status should change to "👀 In Review"

## 🔄 Per-Repository Checklist

Use this checklist for each repository rollout:

### api Repository

- [ ] Create `.github/workflows/project-automation.yml`
- [ ] Set `PROJECT_TOKEN` secret
- [ ] Create labels (`enhancement`, `core-feature`, `priority: blocker`)
- [ ] Test with sample issue
- [ ] Test draft PR workflow
- [ ] Clean up test artifacts
- [ ] Document in README (optional)

### frontend Repository

- [ ] Create `.github/workflows/project-automation.yml`
- [ ] Set `PROJECT_TOKEN` secret
- [ ] Create labels
- [ ] Test with sample issue
- [ ] Test draft PR workflow
- [ ] Clean up test artifacts
- [ ] Document in README (optional)

### contracts Repository

- [ ] Create `.github/workflows/project-automation.yml`
- [ ] Set `PROJECT_TOKEN` secret
- [ ] Create labels
- [ ] Test with sample issue
- [ ] Test draft PR workflow
- [ ] Clean up test artifacts
- [ ] Document in README (optional)

## 🛠️ Customization

### Using Different Labels

If your repository uses different labels, modify the workflow file:

```yaml
jobs:
  automate:
    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main
    secrets:
      PROJECT_TOKEN: ${{ secrets.PROJECT_TOKEN }}
    # Note: Label mapping is in the reusable workflow
    # To customize, fork the workflow or use different labels
```

For custom label mapping, you'll need to modify the reusable workflow in `.github` repository.

### Disabling Specific Events

To disable certain triggers:

```yaml
on:
  issues:
    types:
      - opened
      # Comment out events you don't want:
      # - reopened
      # - closed
  pull_request:
    types:
      - opened
      - ready_for_review
      # - closed
      # - converted_to_draft
  # Disable PR reviews entirely:
  # pull_request_review:
  #   types:
  #     - submitted
```

## 🐛 Troubleshooting

### Workflow not triggering

**Check:**

1. Workflow file is in `.github/workflows/` directory
2. File has `.yml` or `.yaml` extension
3. Syntax is valid (use `yamllint` or GitHub's validator)
4. Events match the ones in the workflow file

### "Bad credentials" error

**Fix:**

1. Verify `PROJECT_TOKEN` secret is set
2. Check PAT hasn't expired
3. Ensure PAT has Organization Projects permission (not just repository)

### Workflow runs but status doesn't update

**Check:**

1. Issue/PR has correct labels
2. PR body contains `Closes #N` for linked issues
3. Project ID and Field ID match in reusable workflow
4. Workflow logs in Actions tab for errors

### Status updates to wrong value

**Verify:**

1. Labels are spelled correctly (case-sensitive)
2. Status option IDs in reusable workflow match your project
3. No conflicting labels on the issue

## 📊 Monitoring

### View Workflow Runs

```bash
# List recent workflow runs
gh run list --repo SecPal/api --workflow "Project Board Automation"

# View specific run
gh run view <run-id> --repo SecPal/api

# View logs
gh run view <run-id> --log --repo SecPal/api
```

### Success Metrics

After deployment, monitor:

- ✅ Workflow success rate (should be >95%)
- ✅ Status updates within 30 seconds
- ✅ No duplicate status updates
- ✅ Proper status transitions

## 🔄 Updating the Workflow

When the reusable workflow in `.github` is updated:

1. **Automatic:** Workflows in other repos automatically use the latest version (because of `@main`)
2. **No action needed** in consuming repositories
3. **Testing:** Always test in `.github` repo first

### Pinning to a Specific Version

For stability, pin to a release tag:

```yaml
uses: SecPal/.github/.github/workflows/project-automation-v2.yml@v1.0.0
```

## 📝 Documentation Updates

After rollout, update each repository's README with:

```markdown
## 🤖 Automation

This repository uses automated project board management. Issues and PRs are
automatically added to the [SecPal Roadmap](https://github.com/orgs/SecPal/projects/1)
with status based on labels and PR state.

See [Project Automation docs](https://github.com/SecPal/.github/blob/main/docs/workflows/PROJECT_AUTOMATION.md)
for details.
```

## ✅ Validation

After deploying to all repositories:

- [ ] All repositories have workflow file
- [ ] All `PROJECT_TOKEN` secrets set and working
- [ ] Labels created in all repos
- [ ] Test issues/PRs created and verified
- [ ] No workflow failures in Actions tab
- [ ] Project board shows correct status for test items
- [ ] README updated with automation info
- [ ] Team notified about new automation

## 🎯 Next Steps

After successful rollout:

1. **Monitor** for 1-2 weeks
2. **Gather feedback** from team
3. **Iterate** on label definitions if needed
4. **Document** any custom workflows
5. **Clean up** test issues/PRs
