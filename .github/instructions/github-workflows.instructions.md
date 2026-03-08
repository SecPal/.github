---
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: AGPL-3.0-or-later
name: GitHub Workflow Rules
description: Applies workflow and Dependabot rules to GitHub automation files in this repo.
applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml,.github/dependabot.yml,.github/dependabot.yaml"
---

# GitHub Actions & Workflow Rules

Applies when editing GitHub Actions workflows, Dependabot configs, and YAML configuration in this repository.

## Workflow Best Practices

- Always set `timeout-minutes` on every job — GitHub default is 6 hours (hangs silently):

  ```yaml
  jobs:
    build:
      timeout-minutes: 15
  ```

- Set **explicit permissions** on every workflow (principle of least privilege). Start with the minimal baseline and add scopes only when a specific job requires them:

  ```yaml
  permissions:
    contents: read
    # Add more granular permissions (e.g., pull-requests: write) only when required by specific jobs
  ```

- **Pin external actions to a specific version**. Prefer full commit SHAs for third-party actions; for GitHub-maintained actions (`actions/*`), pinning to a major version tag is acceptable in this repo (Dependabot keeps them up to date):

  ```yaml
  # ✅ Recommended for third-party actions — pinned to full SHA
  uses: some-org/some-action@11bd71901bbe5b1630ceea73d27597364c9af683 # v1.2.3

  # ✅ Also acceptable in this repo for GitHub-maintained actions
  uses: actions/checkout@v4  # tracked by Dependabot

  # ❌ Bad — floating tag on third-party action, can be hijacked
  uses: some-org/some-action@main
  ```

## Reusable Workflows

- Org-wide reusable workflows live in `workflow-templates/` and `.github/workflows/reusable-*.yml`
- Consume them via:

  ```yaml
  uses: SecPal/.github/.github/workflows/reusable-<name>.yml@main
  ```

- Check `EXAMPLE_workflow_for_other_repos.yml` for reference patterns before writing a new workflow

## `continue-on-error`

- Use `continue-on-error: true` **only** on wait/polling steps, NEVER on test or build steps
- Always add `timeout-minutes` when using `continue-on-error: true` to prevent infinite runs

## Dependabot

- Group minor and patch updates per ecosystem to reduce PR noise:

  ```yaml
  groups:
    minor-and-patch:
      update-types: ["minor", "patch"]
  ```

- Do NOT enable auto-merge for `major` version bumps — these require manual review

## Secrets & Environment Variables

- Reference secrets via `${{ secrets.NAME }}` — never hardcode values
- Use `${{ vars.NAME }}` for non-sensitive configuration values
- Never `echo` secret values in run steps (masked but still bad practice)

## YAML Style

Run `yamllint` before committing workflow changes:

```bash
yamllint .github/workflows/
```
