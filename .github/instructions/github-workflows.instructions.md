---
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: AGPL-3.0-or-later
name: GitHub Workflow Rules
description: Applies focused security and validation criteria to GitHub automation.
applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml,.github/dependabot.yml,.github/dependabot.yaml,workflow-templates/**/*.yml,workflow-templates/**/*.yaml,EXAMPLE_workflow_for_other_repos.yml,tests/*workflow*.sh,tests/dependabot-auto-merge.sh,tests/codeql-applicability.sh,tests/copilot-review-memory*.sh,tests/license-compatibility.sh,tests/prettier-version-alignment.sh,tests/project-automation-core.sh,tests/pull-request-*.sh,tests/reusable-markdown-lint-scope.sh"
---

# GitHub Workflow Review Rules

Apply these criteria only to GitHub Actions workflows, Dependabot configuration,
workflow templates, and their direct validation fixtures.

## Permissions and Execution Bounds

- Declare explicit minimum `permissions` at workflow or job scope. Start with
  no access beyond `contents: read` and add a permission only for the step that
  requires it.
- Set `timeout-minutes` on every job. A reusable-workflow caller job using
  `jobs.<job_id>.uses` cannot set a timeout; the called workflow must bound each
  of its jobs.
- Use `continue-on-error` only for a deliberately non-blocking operation, never
  to hide a failed test, build, security check, or policy check.
- Add concurrency cancellation for superseded runs when it cannot interrupt a
  deployment or another stateful operation unsafely.

## Reproducibility and Supply Chain

- Pin third-party actions to reviewed immutable commit SHAs. GitHub-maintained
  `actions/*` major-version tags are permitted only where Dependabot manages
  updates and repository policy tests allow them.
- Cross-repository reusable workflows must use a reviewed 40-character commit
  SHA. A `governance-ref` that selects scripts or dependencies must resolve to
  that same SHA; mixed governance versions are invalid.
- Do not use productive branch references such as `@main` for cross-repository
  reusable workflows.
- Keep dependency installation reproducible from committed lockfiles. Do not
  download unpinned tools or execute floating packages.

## Secrets and Untrusted Input

- Reference sensitive values through `secrets`; use `vars` only for
  non-sensitive configuration. Never print secrets, tokens, private keys, or
  derived sensitive values.
- Minimize token scope and lifetime. Do not pass write-capable credentials to
  untrusted fork code or check out untrusted code in a privileged
  `pull_request_target` job.
- Treat issue, pull-request, review, and workflow-dispatch fields as untrusted
  input. Pass values through structured action inputs or environment variables,
  not interpolated shell source.

## Dependabot

- Group compatible minor and patch updates where this reduces noise without
  hiding a coupled dependency risk.
- Do not automatically merge major updates. Preserve the repository's explicit
  allowlists, security gates, and review requirements.

## Validation

- Run `actionlint` and YAML validation for changed workflows.
- Run the smallest relevant positive and negative regression fixtures for
  permissions, event trust boundaries, reusable-workflow contracts, and
  timeouts.
- Inspect the complete caller/callee path when changing a reusable workflow.
  Do not infer compatibility from syntax validation alone.
