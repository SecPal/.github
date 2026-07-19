<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Deterministic PR State and Evidence Layer

Governance Package 2.1 provides a deterministic, read-only Git and GitHub data
layer for a later finite pull-request review procedure. It captures canonical
evidence, verifies local Git state, evaluates mechanical merge-gate evidence,
and produces a safely escaped display rendering.

Package 2.1 does not classify technical findings, remediate code, resolve
threads, authorize a merge, or make the finite workflow operational. The
`secpal-pr-review` Codex skill, its finite orchestration, and its installation
belong to Package 2.2 and post-merge acceptance.

## Authority and schemas

The canonical authority is the JSON snapshot and its SHA-256 digest. Markdown
is a derived, non-authoritative view.

- [`secpal-pr-review-snapshot.schema.json`](schemas/secpal-pr-review-snapshot.schema.json)
  defines snapshot version `1.0`.
- [`secpal-pr-review-repositories.schema.json`](schemas/secpal-pr-review-repositories.schema.json)
  defines repository configuration version `1.0`.

The helper validates both structures against these checked-in schemas and then
applies semantic validation such as unique reviewer aliases and evidence digest
verification. Commit evidence must use unique object IDs and contain the
captured PR head commit. Configuration supports a stable canonical identity
with GraphQL, REST/event, numeric, and node-ID aliases; no suffix-sensitive
login is the sole identity contract.

Package 2.1 does not add a production multi-repository registry. Package 2.2
will supply the authoritative runtime registry and must validate each selected
repository configuration against the Package 2.1 configuration schema. The
registry scope must be governed explicitly; it must not be inferred from the
four repositories currently scanned by review-memory automation.

## Canonical digest

The digest is calculated over the complete normalized snapshot after removing
only `snapshot_digest` from its own input. Serialization uses UTF-8, sorted
object keys, deterministic array ordering, no insignificant whitespace, and no
wall-clock capture timestamp or output path. GitHub-provided timestamps remain
evidence. The serialized snapshot itself ends with one newline; that newline is
not part of the digest input.

Identical source and local-checkout evidence therefore produces byte-identical
canonical JSON and the same digest. A local commit becoming available or a
GitHub state change is evidence and can correctly change the digest.

## Commands

Run all commands from the relevant local repository checkout. The helper uses
only the Python standard library.

### Capture a snapshot

```bash
python3 scripts/secpal-pr-review.py snapshot \
  --repo SecPal/.github \
  --pr 123 \
  --config path/to/repository-config.json
```

Canonical JSON is written to standard output by default. A persistent file is
created only when an output option is explicit:

```bash
python3 scripts/secpal-pr-review.py snapshot \
  --repo SecPal/.github \
  --pr 123 \
  --output snapshot.json \
  --markdown-output snapshot.md
```

`--max-api-calls` and `--max-items` may lower or raise the corresponding
configuration limits for one capture. Thread, comment, and reaction caps come
from repository configuration.

### Verify local state

```bash
python3 scripts/secpal-pr-review.py verify-local \
  --repo SecPal/.github \
  --pr 123 \
  --expected-head 0123456789abcdef0123456789abcdef01234567
```

This captures live read-only evidence and then verifies the repository root,
origin identity, clean tracked and untracked state, current branch, configured
upstream, local head, remote-tracking head, PR head, expected head, base
repository and branch, exact base-to-head commit set, commit-object
availability, and every local commit signature.

It never fetches automatically. The helper also sets `GIT_NO_LAZY_FETCH=1` so
a partial clone cannot silently fetch a missing object. It disables replacement
refs and optional locks, and removes inherited Git variables that could select
another repository, worktree, index, object database, shallow boundary,
namespace, injected configuration, subcommand path, or trace-output target.
Normal system, global, and repository configuration still loads from its
standard locations. The `fetched` result is always `false`.

### Verify the mechanical gate

```bash
python3 scripts/secpal-pr-review.py verify-gate \
  --snapshot snapshot.json \
  --config path/to/repository-config.json
```

The gate verifies schema version, digest, complete pagination, an unchanged
repository and pull-request anchor, safe repository and PR identity, the
current signature and check policies, required-check evidence, strict
up-to-date-base requirements, check outcomes, required or requested reviews,
and raw unresolved thread state. It reports separately whether raw unresolved
items exist and whether Package 2.2 technical classification remains necessary.

A clean mechanical result is named `PACKAGE_2_2_CLASSIFICATION_REQUIRED`; it is
not merge readiness or merge authorization. Draft, closed, merged, conflicting,
or not-yet-computed mergeability states block the mechanical gate. GitHub merge
states `DIRTY`, `UNKNOWN`, `BLOCKED`, and `DRAFT` fail closed. `UNSTABLE`
continues through the granular required-check policy so an optional failure is
not promoted into a required failure; `CLEAN` and `HAS_HOOKS` add no merge-state
blocker, while `BEHIND` follows the configured strict up-to-date-base policy.

### Render Markdown

```bash
python3 scripts/secpal-pr-review.py render \
  --snapshot snapshot.json \
  --format markdown
```

Every rendering states:

> Canonical authority: JSON snapshot and SHA-256 digest

## Complete bounded pagination

The snapshot anchors the repository and PR before reading any collection,
advances each connection independently, and reads the complete anchor once more
after all evidence is captured. The anchor includes the PR `updatedAt` value and
the total counts for labels, review requests, reviews, conversation comments,
review threads, and commits. Any lifecycle, identity, update-time, or count
change blocks the capture, and every count must match its fully paginated
collection. It fully paginates:

- labels and requested reviewers or teams;
- review submissions, including informational, approved, dismissed, and
  requested-changes reviews;
- top-level conversation comments and each reaction connection;
- review threads, every nested reply, and each nested reaction connection;
- PR commits and their bounded parent evidence;
- head-commit check runs and status contexts;
- applicable branch rules.

Independent cursors prevent unequal page counts from causing duplicate or
omitted reads. `completeness.fully_paginated_connections` records pages and
items for every completed connection. `completeness.api_calls` and
`completeness.items` record actual bounded work.

The configured defaults are 200 API calls, 10,000 aggregate items, 500 threads,
10,000 comments, and 10,000 reactions. Reaching a cap while `hasNextPage` is
true is never completeness. The helper terminates with
`BLOCKED_INCOMPLETE_REVIEW_STATE` and identifies the exact connection and
cursor. A nested-page failure prevents any authoritative snapshot or requested
output from being emitted.

There are no retries, sleeps, polls, or wait-until-complete loops. One failed
API call is one terminal blocker.

## Signatures

Each PR commit records two independent observations:

1. GitHub's signature type, state, signer, and verification result;
2. local `git verify-commit --raw` evidence when the commit object exists,
   with the signature format derived from the commit's standard ASCII-armor
   header rather than potentially ambiguous verifier status text.

Valid SSH and OpenPGP signatures are accepted when configuration permits them.
The evidence distinguishes `valid`, `invalid`, `unsigned`, `unknown_key`,
`object_unavailable`, and `verification_pending`. An unknown key is never
reported as cryptographically verified. Required invalid, unsigned, unknown,
pending, or unavailable verification blocks the gate. The helper does not
import keys or change signing configuration.

## Required checks

Requiredness is derived from the repository-rule and branch-protection sources
enabled by configuration. Disabled sources are not called. It is not derived
from a hard-coded workflow name or from visible green checks alone. Check runs
and status contexts retain stable GitHub identities and are matched to required
contexts plus application IDs when those IDs are governed. Gate verification
rebuilds requiredness and outcomes from the supplied current policy rather than
trusting capture-time outcome labels. It also retains each configured source's
strict up-to-date policy and blocks a `BEHIND` merge state whenever either
enabled source requires checks against the current base.

Evidence distinguishes required success, pending, failure, and absence;
non-required success, pending, and failure; and unknown requiredness. Required
skipped checks follow the explicit `check_policy.expected_skipped` value. A
missing or inaccessible configured rules source, unsupported check type,
malformed rule, or otherwise unknown requiredness terminates with
`BLOCKED_INCOMPLETE_REVIEW_STATE`. Pending checks are reported once and are not
polled.

## Output and untrusted content

Canonical JSON retains review text as evidence. Derived Markdown escapes
Markdown punctuation, HTML delimiters, code fences, brackets, parentheses,
angle brackets, control characters, and carriage returns. It does not embed
hidden JSON in HTML comments. Only validated `https://github.com` URLs without
unsafe delimiters or credentials are rendered as links; other URLs remain
escaped text.

Explicit outputs use same-directory temporary files, `fsync`, and atomic
replacement. Final mode is `0600`. Existing non-regular targets, output
symlinks, and symlinked parent chains are rejected. Canonical JSON and Markdown
cannot target the same path. Staged temporary files are removed after failure,
and capture failures occur before output preparation.

Diagnostics are structured, bounded, and redact token-, authorization-, key-,
and secret-shaped content. The helper never prints an environment dump or
credential-helper output.

## Strict read-only boundary

External processes use argument arrays and exact command-shape validation.
There is no `shell=True`, shell interpolation, dynamic query construction,
retry loop, or configuration execution. GitHub CLI calls pin `GH_HOST` to
`github.com` and pass `--hostname github.com` explicitly; caller-provided host
overrides and repository-context inference cannot redirect evidence reads.
GraphQL operations are static query documents with variables. Git commands run
with pagers pinned, optional locking disabled, replacement refs ignored, lazy
fetches disabled, and repository- or object-selection environment overrides
removed before process creation. Trace-file and executable-path overrides are
removed as part of the same boundary.

The helper exposes no operation for:

- GraphQL mutations or non-GET REST writes;
- reactions, replies, thread resolution, reviews, or reviewer requests;
- labels, issues, Draft/Ready transitions, or review dispatch;
- commits, pushes, checkouts, branch switches, resets, cleaning, or stashing;
- merges, auto-merge, history rewriting, or force-pushes.

Package 2.1 is also separate from review memory. It neither updates tracking
issues nor promotes historical lessons. Review-memory changes, finding
classification, remediation cycles, GitHub writes, and user-authorized merge
handling are explicit non-goals.

## Exit behavior and testing

- `0` means the requested capture, render, or verification completed without a
  mechanical blocker.
- `2` means invalid or unsafe local input or output handling.
- `3` means a deterministic state, API, completeness, signature, check, or
  review-state blocker.

Offline tests use fake `gh` and fake Git executables. They cover deterministic
serialization, outer and nested pagination with unequal page counts, reactions,
caps, partial failures, signature-envelope classification, update-time and
connection-count anchor races, strict stale-base state, required checks, hostile
rendering, atomic outputs, host pinning, merge-state policy coverage, commit-set
invariants, sanitized Git environments, and executable-call spies that reject
GitHub and Git writes. Live acceptance is a separately identified read-only
phase and never requests an AI review.
