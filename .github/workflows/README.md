<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Reusable Workflows

This directory contains reusable GitHub Actions workflows that can be used across all SecPal repositories.

For cross-repository callers, pin reusable workflows to a reviewed immutable
commit SHA such as `@<trusted-commit-sha>`. Do not copy moving branch refs such
as `@main` into consumer repositories.

## Available Workflows

### Pre-build repository scanning

`.github/actions/trivy-repository-scan` scans an exact clean caller checkout
with pinned Trivy and explicit vulnerability, secret, and misconfiguration
scanners. It emits deterministic, secret-safe evidence under the central policy
and fails closed on unavailable, stale, or malformed scanner evidence. See
[`trivy-repository-scanning.md`](../../docs/trivy-repository-scanning.md) for the
closed caller interface and immutable invocation example.

### Dependabot shared component updates

[SecPal/.github#540](https://github.com/SecPal/.github/issues/540) defines one
technical SemVer line for the shared workflows and actions. The first qualified
release is [v1.1.0](https://github.com/SecPal/.github/releases/tag/v1.1.0).
The historical `v1` tag predates this policy. Pin each shared dependency to the
full release commit SHA and include the exact version as a same-line
`# v1.1.0` comment. Use the same version convention for all eight repositories.

Dependabot proposes each shared component independently. It uses Git tags for
version discovery and can fall back to a branch head when a pinned SHA has no
matching tag. Check GitHub's actual jobs during rollout. Treat the version
comment as a claim until the verifier confirms it against the immutable release.
A shared version can advance while an individual component stays unchanged.
Leave those pins on their current qualified release until the component changes.

The already pinned protected verifier compares the consumer's exact signed diff
and the relevant Git trees. It authenticates the immutable GitHub Release, its
tag and commit, and its native release attestation for both pins. Compatible
implementation changes to reviewed read-only closures can enroll in native
auto-merge under the caller's policy. The consumer's required checks still
decide whether GitHub can merge. A qualified release with an unchanged closure
does not enroll. During migration the existing legacy no-op policy applies to
unannotated pins.

Keep the merge workflow, its caller, and security-sensitive authority changes
on the independently reviewed path. The already trusted verifier never admits
an `AUTHORITY_CHANGED` proposal for automatic enrollment. Record the exact
released SHA, affected component and consuming scope on the protected adoption
PR, and use the existing maintainer review and merge path.

#### Publication

Organization owners publish with the existing administrative GitHub CLI from
an isolated checkout. The repository restricts numeric version tag creation
to organization owners. Create the tag in the native release publication
operation so there is no pre-existing unpublished version tag.

Review the consumer-visible closure delta from the preceding verified release
first. Check the exported workflow or action, the exact nested calls, scripts,
runtime manifests, schemas and policies it loads, and the scope of any
authority changes. Release only when this review identifies an actual
consumer-visible change. Pin refreshes in the repository's local callers and
unrelated documentation do not qualify. Keep the authority caller pinned to
the separately accepted revision.

Run `scripts/publish-shared-components.sh VERSION SHA NOTES_FILE` from the
canonical repository. The notes should identify the accepted changes and their
consumer scope. The command requires a signed protected-main merge with green
required checks, rejects a candidate without a shared-source delta, and
verifies the resulting GitHub attestation and exact tag/commit binding. Use a
patch for compatible fixes, a minor for compatible additions, and a major for
breaking changes.

### Dependabot manifest coverage

`reusable-dependabot-manifest-coverage.yml` runs the shared, deterministic
manifest-coverage and cadence-policy assertions as separate checks. Callers
pin this workflow to a reviewed immutable commit and keep repository-local
policy in `.github/dependabot-manifest-exceptions.yml`. The coverage job accepts
that policy only from a separate protected-default-branch checkout; policy
newly proposed in the subject revision cannot authorize itself. See
[`dependabot-manifest-coverage.md`](../../docs/dependabot-manifest-coverage.md)
for the contract and invocation example.

### Released-artifact vulnerability re-evaluation

`reusable-vulnerability-reevaluation.yml` verifies and re-evaluates one exact
OCI index/platform subject with pinned Grype and Trivy, fresh vulnerability
data, authoritative Syft SPDX association, central policy, and bounded evidence.
Credentialed access is limited to the authenticated caller's GHCR namespace.
The Actions run reports the verdict after retaining evidence. See
[`released-artifact-vulnerability-reevaluation.md`](../../docs/released-artifact-vulnerability-reevaluation.md)
for exact inputs, permissions, daily/manual caller examples, evidence output,
and fail-closed semantics.

### Core Workflows

#### `reusable-reuse.yml`

Checks REUSE 3.3 compliance for copyright and licensing information.

**Usage:**

```yaml
jobs:
  reuse:
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@<trusted-commit-sha>
```

#### `reusable-license-compatibility.yml`

Checks that all licenses are compatible with AGPL-3.0-or-later.

**Usage:**

```yaml
jobs:
  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@<trusted-commit-sha>
```

#### `reusable-prettier.yml`

Checks code formatting with Prettier.

When a repository has a `package.json`, the workflow uses `npm ci` by default and falls back to `npm install` with a warning if `package-lock.json` is missing. Set `require-lockfile: true` to make missing lock files fail the workflow.

**Usage:**

```yaml
jobs:
  prettier:
    uses: SecPal/.github/.github/workflows/reusable-prettier.yml@<trusted-commit-sha>
    with:
      node-version: "26.x" # optional, default: '26.x'
      files: "**/*.{md,yml,yaml,json}" # optional
      require-lockfile: false # optional, default: false
```

#### `reusable-markdown-lint.yml`

Lints Markdown files.

**Usage:**

```yaml
jobs:
  markdown-lint:
    uses: SecPal/.github/.github/workflows/reusable-markdown-lint.yml@<trusted-commit-sha>
```

### Frontend Workflows (Node.js/React)

#### `reusable-node-test.yml`

Runs Node.js tests.

**Usage:**

```yaml
jobs:
  test:
    uses: SecPal/.github/.github/workflows/reusable-node-test.yml@<trusted-commit-sha>
    with:
      node-version: "26.x" # optional, default: '26.x'
      install-command: "npm ci" # optional
      test-command: "npm test" # optional
```

#### `reusable-node-lint.yml`

Runs Node.js linting (ESLint).

**Usage:**

```yaml
jobs:
  lint:
    uses: SecPal/.github/.github/workflows/reusable-node-lint.yml@<trusted-commit-sha>
    with:
      node-version: "26.x" # optional, default: '26.x'
      lint-command: "npm run lint" # optional
```

#### `reusable-node-build.yml`

Builds Node.js project.

**Usage:**

```yaml
jobs:
  build:
    uses: SecPal/.github/.github/workflows/reusable-node-build.yml@<trusted-commit-sha>
    with:
      node-version: "26.x" # optional, default: '26.x'
      build-command: "npm run build" # optional
```

### Backend Workflows (PHP/Laravel)

#### `reusable-php-lint.yml`

Checks PHP code style with Laravel Pint.

**Usage:**

```yaml
jobs:
  pint:
    uses: SecPal/.github/.github/workflows/reusable-php-lint.yml@<trusted-commit-sha>
    with:
      php-version: "8.4" # optional, default: '8.4'
      pint-command: "./vendor/bin/pint --test" # optional
```

#### `reusable-php-stan.yml`

Runs static analysis with PHPStan.

**Usage:**

```yaml
jobs:
  phpstan:
    uses: SecPal/.github/.github/workflows/reusable-php-stan.yml@<trusted-commit-sha>
    with:
      php-version: "8.4" # optional, default: '8.4'
      phpstan-command: "./vendor/bin/phpstan analyse" # optional
```

## Example: Complete CI Workflow for Frontend

```yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main

jobs:
  reuse:
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@<trusted-commit-sha>

  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@<trusted-commit-sha>

  prettier:
    uses: SecPal/.github/.github/workflows/reusable-prettier.yml@<trusted-commit-sha>

  markdown-lint:
    uses: SecPal/.github/.github/workflows/reusable-markdown-lint.yml@<trusted-commit-sha>

  lint:
    uses: SecPal/.github/.github/workflows/reusable-node-lint.yml@<trusted-commit-sha>

  test:
    uses: SecPal/.github/.github/workflows/reusable-node-test.yml@<trusted-commit-sha>

  build:
    uses: SecPal/.github/.github/workflows/reusable-node-build.yml@<trusted-commit-sha>
```

## Example: Backend Quality Checks

```yaml
name: CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main

jobs:
  reuse:
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@<trusted-commit-sha>

  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@<trusted-commit-sha>

  pint:
    uses: SecPal/.github/.github/workflows/reusable-php-lint.yml@<trusted-commit-sha>

  phpstan:
    uses: SecPal/.github/.github/workflows/reusable-php-stan.yml@<trusted-commit-sha>
```

### Workflow Linting

### `reusable-actionlint.yml`

Lints GitHub Actions workflows with actionlint and shellcheck.

**Usage:**

```yaml
jobs:
  actionlint:
    uses: SecPal/.github/.github/workflows/reusable-actionlint.yml@<trusted-commit-sha>
```
