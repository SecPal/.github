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
authoritative. Generated, untracked output is absent by construction. A
tracked manifest is never suppressed merely because a directory is named
`build`, `vendor`, `dist`, or another conventional output name. A genuinely
generated tracked manifest needs the same exact protected-history exception as
any other manifest. Repository-relative paths must already be normalized POSIX
paths. Manifest candidates that are symbolic links fail closed rather than
resolving outside the authoritative tree.

[`policies/dependabot-manifest-catalog-v1.json`](../policies/dependabot-manifest-catalog-v1.json)
is the sole executable ecosystem and path-pattern authority. Code, workflows,
tests, and this document do not carry a second taxonomy.

The current catalog was reviewed on 2026-09-02 against:

- GitHub's [supported ecosystems reference](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories);
- GitHub's [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference);
- Dependabot Core commit
  [`eb6370bc47da4ab268ae36d2af8ccc27a3c98a4e`](https://github.com/dependabot/dependabot-core/tree/eb6370bc47da4ab268ae36d2af8ccc27a3c98a4e),
  specifically the cataloged file-fetcher and shared behavior sources.

The catalog's `upstream.dependabot_core_source_paths` array records every exact
source inspected at that commit. Every executable manifest rule carries its
own `source_paths` binding, and every supported configuration ecosystem has one
machine-checked discovery disposition. A catalog is invalid if an ecosystem
lacks a disposition, an executable rule lacks provenance, or a provenance path
is not in the catalog authority set. Shared matching behavior such as
`exclude-paths` is bound separately through `behavior_provenance`, and unused
source claims are rejected. NuGet is explicitly marked as not directly
discoverable without reproducing its native solution/project workspace model;
high-confidence native NuGet entry points fail as unclassified candidates
instead of disappearing.

Consumer runs use this immutable snapshot. They do not download mutable
documentation or code.

## Anti-silent-drift behavior

The future-support invariant has three independent fail-closed controls:

1. Catalog loading proves that every supported ecosystem has direct, shared,
   or explicitly unavailable discovery authority.
2. Bounded, high-confidence candidate rules report
   `UNCLASSIFIED_MANIFEST_CANDIDATE` when a dependency-like tracked file cannot
   be classified safely.
3. Every catalog has a fixed expiry. Runs after that date report
   `CATALOG_STALE` until a reviewer compares the catalog with current upstream
   sources, updates its provenance and rules, and sets a new bounded expiry.

This makes unknown support bounded rather than silently accepted forever. A
candidate must be classified in the central catalog or removed; a manifest
exception cannot classify it. Generic files such as `build.yaml`,
`packages.json`, and `modules.toml` are not candidates without dependency
evidence. Ambiguous infrastructure files fail closed at module scope. A module
containing `.tofu` selects OpenTofu; a `.tf`-only module needs one protected
directory classification (`directory: /` is the sole representation for the
repository root), and contradictory per-directory ownership is rejected.

## Coverage semantics

The guard structurally parses `.github/dependabot.yml` (or the `.yaml` spelling)
with a safe YAML schema and a closed semantic contract. It rejects malformed
input, duplicate relevant entries, unknown fields in the structures it owns,
unknown ecosystems, invalid `directory` or `directories` values, and ambiguous
overlap for a discovered manifest.

Coverage requires both the expected `package-ecosystem` and the manifest's
effective Dependabot directory. A `directory` is an exact update root, not a
filesystem prefix. `directories` supports GitHub's documented `*` and `**`
forms, including `"**/*"` without a leading slash. `exclude-paths` uses
Dependabot's file, directory-prefix, single-segment, and recursive matching,
relative to the effective update directory. An excluded manifest is not
covered.

An absent `target-branch` means the authenticated repository default branch.
An explicit `target-branch` covers the checked state only when it equals that
same default branch. The reusable workflow obtains this value from GitHub's
repository event context; the local CLI value is an explicit simulation input,
not authorization evidence.

GitHub Actions workflows in `.github/workflows` derive `/`, matching
Dependabot's documented root special case. Ecosystem-specific ownership is
applied where pinned fetchers require it: npm and Cargo workspace members derive
their matched workspace root, while excluded or undeclared nested manifests keep
independent ownership. Workspace patterns match complete paths relative to the
candidate root rather than arbitrary basenames. Terraform/OpenTofu ownership
applies to the whole effective module directory. Other primary manifests derive
their direct parent directory. Therefore npm coverage for `/tools` cannot cover
an unrelated `frontend/package.json`, while npm or Cargo coverage for `/` covers
a declared root workspace member.

Dependabot Core recognizes names containing `Dockerfile` or `Containerfile`
under its `docker` package ecosystem. The SecPal catalog preserves that exact
terminology:

```text
image/Containerfile -> ecosystem docker, directory /image
```

`docker` is Dependabot nomenclature only. It does not imply a Docker runtime or
change SecPal's Podman, Buildah, or OCI architecture.

## Reviewed exceptions and classifications

Repository-local policy data lives in
`.github/dependabot-manifest-exceptions.yml`:

```yaml
version: 1
classifications:
  - directory: infrastructure
    ecosystem: opentofu
    reason: Protected history assigns this complete module to OpenTofu.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
manifest-exceptions:
  - manifest: legacy/composer.json
    ecosystem: composer
    reason: The upstream registry is unavailable during the bounded migration.
    reviewed-by: "@SecPal/maintainers"
    reviewed-on: "2026-09-02"
```

Manifest exceptions bind an exact normalized path, one catalog ecosystem, a
bounded reason, reviewer identity, and real non-future review date. Module
classifications bind one exact normalized directory and either Terraform or
OpenTofu. Wildcards, parent traversal, duplicate records, and unknown
ecosystems are invalid.

The metadata strings do not authenticate their own review. Hosted enforcement
loads usable policy only from a separate checkout of the protected default
branch. Policy newly proposed in the subject change cannot exempt that same
change; an attempted self-exemption is reported as `UNTRUSTED_POLICY_INPUT`.
This permits a policy-only staging change to pass before the protected policy
is needed. The repository's protected merge history supplies the review
authority; `reviewed-by` and `reviewed-on` remain auditable metadata within that
authority. Local execution must pass `--trusted-policy-root` to model such a
baseline. Without it, a local subject policy is parsed fail-closed but never
grants an exception.

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
  --repository SecPal/example --default-branch main \
  --trusted-policy-root /path/to/protected-baseline --format json
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
revision; a caller cannot replace them with scripts from its own checkout. A
third data-only checkout obtains exception/classification authority from the
repository default branch. GitHub supplies both the repository identity and
default-branch identity; neither is a caller workflow input.

## Non-goals

This contract does not adopt Dependabot in any repository, modify downstream
Dependabot configuration, enable auto-merge, introduce Renovate, change runtime
container architecture, scan source vulnerabilities, or mutate providers or
production systems. Repository descendants own adoption after this shared
contract is merged.
