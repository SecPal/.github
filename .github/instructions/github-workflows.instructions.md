---
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: AGPL-3.0-or-later
applyTo: "**/*.yml,**/*.yaml"
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

- Set **explicit permissions** on every workflow (principle of least privilege):

  ```yaml
  permissions:
    contents: read
    pull-requests: write
  ```

- **Pin external actions to full SHA**, not floating tags:

  ```yaml
  # ✅ Good — pinned to SHA
  uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

  # ❌ Bad — floating tag, can be hijacked
  uses: actions/checkout@v4
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
