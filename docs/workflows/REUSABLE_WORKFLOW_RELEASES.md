<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Reusable Workflow Releases

The reusable workflows in this repository are a versioned integration surface.
Each published release uses one complete semantic-version tag in the form
`v<major>.<minor>.<patch>`.

## Release Contract

- Publish every reusable-workflow release as an immutable GitHub Release.
  Repository administrators must enable immutable releases before publishing.
- Create only annotated, signed tags. Never move, delete, or reuse a published
  tag.
- Record the release tag's resolved commit SHA in the release notes. Reviewers
  use that SHA to audit the exact workflow code selected by the tag.
- Do not use major-only tags such as `v1`, branch names, or other moving refs
  for cross-repository workflow calls.
- Increment the major version for incompatible caller contracts, the minor
  version for backward-compatible behavior or inputs, and the patch version
  for backward-compatible fixes.

## Consumer Usage

Use a published immutable release tag in the `uses:` reference so Dependabot
can determine the numeric update type:

```yaml
jobs:
  quality:
    uses: SecPal/.github/.github/workflows/reusable-node-build.yml@v2.0.0
```

Before merging a Dependabot update, verify that the tag resolves to the
resolved commit SHA recorded in the upstream immutable release. A release tag
is therefore both machine-readable for Dependabot and auditable as a specific
immutable commit.

## Initial Migration

The legacy `v1` tag is stale and must not be reused. Publish the first current
release as `v2.0.0`, then migrate every consumer repository in its own pull
request. Do not mix that migration with unrelated dependency changes.
