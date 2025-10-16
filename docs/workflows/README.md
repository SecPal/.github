<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Workflow Documentation

This directory contains documentation for GitHub Actions workflows used in this repository.

## Structure

Workflow **code** lives in `.github/workflows/*.yml`
Workflow **documentation** lives here in `docs/workflows/*.md`

This separation allows updating documentation without triggering workflow approval requirements.

## Available Workflows

- **[Copilot Review Enforcement](./copilot-enforcement.md)** - Automated code review system using GitHub Copilot
  - Workflow: `.github/workflows/copilot-review.yml` + `reusable-copilot-review.yml`
  - Enforces Copilot review before merging PRs

## Why This Structure?

GitHub requires approval for any changes to files in `.github/workflows/`, even documentation.

By keeping docs separate:

- ✅ Documentation updates don't require workflow approval
- ✅ Clear separation between code and docs
- ✅ Easier to maintain and update
- ✅ Workflows directory stays focused on YAML files
