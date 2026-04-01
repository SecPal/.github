<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Reusable Workflows

This directory contains reusable GitHub Actions workflows that can be used across all SecPal repositories.

## Available Workflows

### Core Workflows

#### `reusable-reuse.yml`

Checks REUSE 3.3 compliance for copyright and licensing information.

**Usage:**

```yaml
jobs:
  reuse:
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@main
```

#### `reusable-license-compatibility.yml`

Checks that all licenses are compatible with AGPL-3.0-or-later.

**Usage:**

```yaml
jobs:
  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@main
```

#### `reusable-prettier.yml`

Checks code formatting with Prettier.

When a repository has a `package.json`, the workflow uses `npm ci` by default and falls back to `npm install` with a warning if `package-lock.json` is missing. Set `require-lockfile: true` to make missing lock files fail the workflow.

**Usage:**

```yaml
jobs:
  prettier:
    uses: SecPal/.github/.github/workflows/reusable-prettier.yml@main
    with:
      node-version: "22.x" # optional, default: '22.x'
      files: "**/*.{md,yml,yaml,json}" # optional
      require-lockfile: false # optional, default: false
```

#### `reusable-markdown-lint.yml`

Lints Markdown files.

**Usage:**

```yaml
jobs:
  markdown-lint:
    uses: SecPal/.github/.github/workflows/reusable-markdown-lint.yml@main
```

### Frontend Workflows (Node.js/React)

#### `reusable-node-test.yml`

Runs Node.js tests.

**Usage:**

```yaml
jobs:
  test:
    uses: SecPal/.github/.github/workflows/reusable-node-test.yml@main
    with:
      node-version: "22.x" # optional, default: '22.x'
      install-command: "npm ci" # optional
      test-command: "npm test" # optional
```

#### `reusable-node-lint.yml`

Runs Node.js linting (ESLint).

**Usage:**

```yaml
jobs:
  lint:
    uses: SecPal/.github/.github/workflows/reusable-node-lint.yml@main
    with:
      node-version: "22.x" # optional, default: '22.x'
      lint-command: "npm run lint" # optional
```

#### `reusable-node-build.yml`

Builds Node.js project.

**Usage:**

```yaml
jobs:
  build:
    uses: SecPal/.github/.github/workflows/reusable-node-build.yml@main
    with:
      node-version: "22.x" # optional, default: '22.x'
      build-command: "npm run build" # optional
```

### Backend Workflows (PHP/Laravel)

#### `reusable-php-test.yml`

Runs PHP tests with PEST.

**Usage:**

```yaml
jobs:
  test:
    uses: SecPal/.github/.github/workflows/reusable-php-test.yml@main
    with:
      php-version: "8.4" # optional, default: '8.4'
      test-command: "./vendor/bin/pest" # optional
```

#### `reusable-php-lint.yml`

Checks PHP code style with Laravel Pint.

**Usage:**

```yaml
jobs:
  pint:
    uses: SecPal/.github/.github/workflows/reusable-php-lint.yml@main
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
    uses: SecPal/.github/.github/workflows/reusable-php-stan.yml@main
    with:
      php-version: "8.4" # optional, default: '8.4'
      phpstan-command: "./vendor/bin/phpstan analyse" # optional
```

### Contracts Workflows (OpenAPI)

#### `reusable-openapi-lint.yml`

Validates OpenAPI specifications.

When a repository has a `package.json`, the workflow uses `npm ci` by default and falls back to `npm install` with a warning if `package-lock.json` is missing. Set `require-lockfile: true` to make missing lock files fail the workflow.

**Usage:**

```yaml
jobs:
  openapi-lint:
    uses: SecPal/.github/.github/workflows/reusable-openapi-lint.yml@main
    with:
      openapi-file: "openapi.yaml" # optional, default: 'openapi.yaml'
      node-version: "22.x" # optional, default: '22.x'
      require-lockfile: false # optional, default: false
```

## Internal Helper Actions

### `setup-node-with-deps`

Internal composite action used by the reusable Node-based validation workflows to keep Node setup, `jq` installation, and lockfile-aware npm installation behavior consistent.

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
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@main

  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@main

  prettier:
    uses: SecPal/.github/.github/workflows/reusable-prettier.yml@main

  markdown-lint:
    uses: SecPal/.github/.github/workflows/reusable-markdown-lint.yml@main

  lint:
    uses: SecPal/.github/.github/workflows/reusable-node-lint.yml@main

  test:
    uses: SecPal/.github/.github/workflows/reusable-node-test.yml@main

  build:
    uses: SecPal/.github/.github/workflows/reusable-node-build.yml@main
```

## Example: Complete CI Workflow for Backend

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
    uses: SecPal/.github/.github/workflows/reusable-reuse.yml@main

  license-check:
    uses: SecPal/.github/.github/workflows/reusable-license-compatibility.yml@main

  pint:
    uses: SecPal/.github/.github/workflows/reusable-php-lint.yml@main

  phpstan:
    uses: SecPal/.github/.github/workflows/reusable-php-stan.yml@main

  test:
    uses: SecPal/.github/.github/workflows/reusable-php-test.yml@main
```

### Workflow Linting

### `reusable-actionlint.yml`

Lints GitHub Actions workflows with actionlint and shellcheck.

**Usage:**

```yaml
jobs:
  actionlint:
    uses: SecPal/.github/.github/workflows/reusable-actionlint.yml@main
```
