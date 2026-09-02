<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Dependabot Manifest Coverage Contract

## Goal and failure model

The shared guard proves that every active, tracked dependency manifest known to
the SecPal policy is covered by a Dependabot entry with the same ecosystem and
actual Dependabot directory scope, or by one exact reviewed exception. It also
fails when a dependency-manifest candidate cannot be classified safely.

The guard is designed to detect these failures:

- a manifest is added without Dependabot coverage;
- an entry for the right ecosystem points at an unrelated directory;
- an entry for the right directory uses an unrelated ecosystem;
- comments or malformed YAML appear to provide coverage;
- overlapping entries make ownership ambiguous;
- a broad exception hides manifests that were not individually reviewed;
- upstream manifest knowledge becomes stale or a likely manifest is unknown;
- cadence drifts independently of otherwise correct manifest coverage.

It parses repository files as data and never executes repository dependency
code.

## Discovery and catalog authority

Discovery uses `git ls-files -z`, so only version-controlled source state is
authoritative. Generated, untracked output is absent by construction. The
catalog also excludes tracked paths under defined cache, vendor, and build
trees. Repository-relative paths must already be normalized POSIX paths.
Manifest candidates that are symbolic links fail closed rather than resolving
outside the authoritative tree.

[`policies/dependabot-manifest-catalog-v1.json`](../policies/dependabot-manifest-catalog-v1.json)
is the sole executable ecosystem and path-pattern authority. Code, workflows,
tests, and this document do not carry a second taxonomy.

The current catalog was reviewed on 2026-09-02 against:

- GitHub's [supported ecosystems reference](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories);
- GitHub's [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference);
- Dependabot Core commit
  [`eb6370bc47da4ab268ae36d2af8ccc27a3c98a4e`](https://github.com/dependabot/dependabot-core/tree/eb6370bc47da4ab268ae36d2af8ccc27a3c98a4e),
  specifically the relevant `file_fetcher.rb` implementations for Docker,
  Docker Compose, GitHub Actions, npm, Composer, Python, Gradle, pre-commit,
  Terraform, and OpenTofu.

The catalog's `upstream.dependabot_core_source_paths` array records every exact
file-fetcher path inspected at that commit; catalog refreshes update this list
alongside the commit identity.

Consumer runs use this immutable snapshot. They do not download mutable
documentation or code.

## Anti-silent-drift behavior

The future-support invariant has two independent fail-closed controls:

1. Broad, versioned candidate rules report
   `UNCLASSIFIED_MANIFEST_CANDIDATE` when a dependency-like tracked file cannot
   be classified safely.
2. Every catalog has a fixed expiry. Runs after that date report
   `CATALOG_STALE` until a reviewer compares the catalog with current upstream
   sources, updates its provenance and rules, and sets a new bounded expiry.

This makes unknown support bounded rather than silently accepted forever. A
candidate must be classified in the central catalog or removed; a repository
exception cannot classify it. Ambiguous files also fail closed. In particular,
`.tf` is supported by both Terraform and OpenTofu and therefore needs an exact
reviewed classification in the repository exception file. A `.tofu` manifest
classifies directly as OpenTofu.

## Coverage semantics

The guard structurally parses `.github/dependabot.yml` (or the `.yaml` spelling)
with a safe YAML schema and a closed semantic contract. It rejects malformed
input, duplicate relevant entries, unknown fields in the structures it owns,
unknown ecosystems, invalid `directory` or `directories` values, and ambiguous
overlap for a discovered manifest.

Coverage requires both the expected `package-ecosystem` and the manifest's
Dependabot directory. A `directory` is an exact manifest directory, not a
filesystem prefix. `directories` supports deterministic `*` and `**` glob
matching. An entry targeting another branch or excluding the manifest does not
cover the checked source tree.

GitHub Actions workflows in `.github/workflows` derive `/`, matching
Dependabot's documented root special case. Other manifests derive their direct
parent directory. Therefore npm coverage for `/tools` cannot cover
`frontend/package.json`, and an entry for `/` cannot cover that nested npm
manifest merely because `/` is its filesystem ancestor.

Dependabot Core recognizes names containing `Dockerfile` or `Containerfile`
under its `docker` package ecosystem. The SecPal catalog preserves that exact
terminology:

```text
image/Containerfile -> ecosystem docker, directory /image
```

`docker` is Dependabot nomenclature only. It does not imply a Docker runtime or
change SecPal's Podman, Buildah, or OCI architecture.

## Reviewed exceptions and classifications

Repository-local review data lives in
`.github/dependabot-manifest-exceptions.yml`:

```yaml
version: 1
classifications:
  - manifest: infrastructure/main.tf
    ecosystem: opentofu
    reason: OpenTofu owns this reviewed HCL module.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
manifest-exceptions:
  - manifest: legacy/composer.json
    ecosystem: composer
    reason: The upstream registry is unavailable during the bounded migration.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
```

Every record binds an exact normalized manifest path, one catalog ecosystem, a
bounded reason, reviewer identity, and review date. Wildcards, parent traversal,
duplicate records, and unknown ecosystems are invalid. A classification only
resolves a catalog-proven ambiguity; it cannot introduce an arbitrary ecosystem
for an otherwise unknown candidate.

The optional `no-applicable-manifest` record has only reason and review
metadata. It is accepted solely when discovery finds neither an applicable
manifest nor an unclassified candidate. It cannot suppress a discovered file.

Remove an exception in the same repository change that makes its manifest
supportable. If the manifest is obsolete, remove the manifest rather than retain
it solely for Dependabot.

## Coverage and cadence are separate assertions

`coverage` answers whether each manifest is covered or exactly excepted.
`cadence` independently validates each effective update schedule against:

```text
interval: daily
time: 04:00
timezone: Europe/Berlin
```

A covered manifest can pass `MANIFEST_COVERAGE` while its update entry fails
`CADENCE_POLICY`. Multi-ecosystem entries use their group's effective schedule.

Run the assertions locally with:

```bash
node scripts/secpal-dependabot-manifest-coverage.mjs coverage \
  --repository SecPal/example --format json
node scripts/secpal-dependabot-manifest-coverage.mjs cadence \
  --repository SecPal/example --format json
```

Both commands return a stable ordered JSON document with assertion, status,
repository, catalog identity, manifest path, expected ecosystem, matched
configuration, mismatch reason, and accepted exception path. Text output is a
concise projection of the same diagnostics. A failed assertion exits with
status 1.

## Reusable workflow

Consumers pin the workflow to a reviewed immutable SecPal/.github commit:

```yaml
jobs:
  dependabot-manifest-coverage:
    uses: SecPal/.github/.github/workflows/reusable-dependabot-manifest-coverage.yml@0123456789abcdef0123456789abcdef01234567
```

The reusable workflow exposes separate `Manifest Coverage` and `Cadence Policy`
jobs. It begins with `permissions: {}`, grants only `contents: read` per job,
sets bounded timeouts, and pins all external actions to immutable full SHAs with
reviewed release annotations.

The subject repository is checked out only as data. A second checkout derives
the governance repository and revision from the called workflow's
`job.workflow_repository` and `job.workflow_sha`. The engine, catalog, lockfile,
and parser dependencies always come from that immutable called-workflow
revision; a caller cannot replace them with scripts from its own checkout.

## Non-goals

This contract does not adopt Dependabot in any repository, modify downstream
Dependabot configuration, enable auto-merge, introduce Renovate, change runtime
container architecture, scan source vulnerabilities, or mutate providers or
production systems. Repository descendants own adoption after this shared
contract is merged.
