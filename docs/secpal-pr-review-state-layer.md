<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Deterministic PR State and Evidence Layer

Governance Package 2.1 provides a deterministic, read-only Git and GitHub data
layer for a later finite pull-request review procedure. It captures canonical
evidence, verifies immutable snapshot evidence and local Git state, evaluates
open-pull-request merge-gate evidence, and produces a safely escaped display
rendering.

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
verification. Repository owner, name, URL, PR URL, base repository, head
repository, and merged-state components must be internally consistent. Commit
evidence must use unique object IDs and contain the captured PR head commit.
Reviews, conversation comments, review threads, inline comments, and reactions
must also have unique stable GitHub identities. Complete required-check
evidence cannot carry an unknown reason.
Stored anchor counts must exactly match all supplied top-level PR collections,
including the complete commit set. Configuration
supports a stable canonical identity with GraphQL, REST/event, numeric, and
node-ID aliases. An alias may appear in multiple namespaces for the same
canonical identity, but it cannot identify different reviewers; no
suffix-sensitive login is the sole identity contract.
Configuration and snapshot files must have JSON objects at their roots; every
other valid JSON root produces the same structured invalid-input response as a
schema violation.

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

SHA-256 provides deterministic integrity and equality evidence; it is not a
signature or message-authentication code and does not authenticate who produced
a snapshot. Callers must obtain gate input from the trusted capture execution
or a separately authenticated artifact channel.

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

Repository configuration deliberately contains no arbitrary local-validation
command list. Executing repository-selected programs would cross this layer's
strict read-only process boundary; Package 2.2 owns orchestration of the
repository's documented test and validation commands.

It never fetches automatically. The helper also sets `GIT_NO_LAZY_FETCH=1` so
a partial clone cannot silently fetch a missing object. It disables replacement
refs and optional locks, and removes inherited Git variables that could select
another repository, worktree, index, object database, shallow boundary,
namespace, injected configuration, subcommand path, or trace-output target.
Every `git` and `gh` invocation uses a resolved absolute executable from fixed
host-tool prefixes; the inherited `PATH` is replaced for the command and any
configured verifier child process. Standard Git configuration still loads, but
`core.fsmonitor` is disabled and the OpenPGP, SSH, and X.509 verifier programs
are pinned to their standard names within that trusted command path. Standard
input is closed and each external command has a 30-second timeout. The
`fetched` result is always `false`.

### Verify immutable evidence

```bash
python3 scripts/secpal-pr-review.py verify-evidence \
  --snapshot snapshot.json \
  --config path/to/repository-config.json
```

`verify-evidence` validates the schema, canonical digest, repository and PR
identity, stable head anchors, lifecycle-state consistency, captured commit
set, signature policy, applicable-rule evidence, required-check identities and
outcomes, configured capture caps, pagination completeness, and raw review
state. It is suitable for open, closed, and merged snapshots, including
historical read-only audits and post-merge acceptance.

A merged snapshot must consistently report `state: MERGED`, `is_merged: true`,
`is_draft: false`, and equal before/after head OIDs. Post-merge
`mergeable: UNKNOWN` or `null` and `merge_state_status: UNKNOWN` do not make
otherwise complete immutable evidence invalid: those live merge-candidate
fields are no longer meaningful after merge. The final PR head must still be
present in the captured commit evidence, and every configured signature,
ruleset, branch-protection, required-check, cap, and completeness policy
continues to apply.

The structured report uses `EVIDENCE_VERIFIED` only when the evidence contract
and current repository policy succeed. It always sets `merge_authorized` to
`false`, retains raw review counts and effective review state, and states when
Package 2.2 technical classification remains necessary. Unresolved or
historical review evidence is reported rather than silently discarded;
evidence integrity alone does not classify a finding or establish merge
readiness.

### Verify the open-PR mechanical gate

```bash
python3 scripts/secpal-pr-review.py verify-gate \
  --snapshot snapshot.json \
  --config path/to/repository-config.json
```

The gate first invokes the same evidence-verification path as
`verify-evidence`. It then adds current merge-candidate requirements for an
open, non-Draft PR: an available head branch, mergeable state, safe GitHub merge
state, strict up-to-date-base requirements, and the absence of required,
requested, or unresolved review blockers. Direct PR reactions remain visible
even when no review or comment accompanies them.

The current repository configuration is authoritative at gate time. Recorded
API calls, aggregate items, threads, comments, and reactions must fit its current
caps even when the snapshot was captured under looser limits. If a rule source
required by the current configuration was not captured, the gate retains the
snapshot digest and all accumulated blockers in its structured report and does
not attempt to infer missing required checks from placeholder evidence.

A clean open-PR mechanical result is named
`PACKAGE_2_2_CLASSIFICATION_REQUIRED`; it is not merge authorization. Draft,
closed, merged, conflicting, or not-yet-computed mergeability states block this
open-PR gate. A closed or merged PR receives the lifecycle blocker without
having its post-merge mergeability values reinterpreted as evidence-integrity
failures. GitHub merge states `DIRTY`, `UNKNOWN`, `BLOCKED`, and `DRAFT` fail
closed for an open candidate. `UNSTABLE`
continues through the granular required-check policy so an optional failure is
not promoted into a required failure; `CLEAN` and `HAS_HOOKS` add no merge-state
blocker, while `BEHIND` follows the configured strict up-to-date-base policy.

In short: `verify-evidence` validates evidence integrity; `verify-gate`
additionally evaluates open-PR merge readiness. Neither command authorizes
merge.

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
advances each connection independently, reads the complete anchor after the
initial capture, and reads it a third time after revalidation. The anchor
includes the PR `updatedAt` value and the total counts for labels, review
requests, reviews, direct PR reactions, conversation comments, review threads,
and commits. Any
lifecycle, identity, update-time, or count change blocks the capture, and every
count must match its fully paginated collection. The normalized counts are
retained as `pull_request.captured_connection_counts` and validated again
whenever a snapshot is loaded. It fully paginates:

- labels and requested reviewers or teams;
- review submissions, including informational, approved, dismissed, and
  requested-changes reviews, plus each review-summary reaction connection;
- the pull-request body and its direct reaction connection;
- top-level conversation comments and each reaction connection;
- review threads, every nested reply, and each nested reaction connection;
- PR commits and their bounded parent evidence;
- check runs and status contexts from GitHub's effective check commit;
- applicable branch rules.

After the first anchor comparison, the helper performs a second complete,
bounded observation of every fully paginated PR collection and of volatile
evidence that can change without moving the PR head or its top-level counts.
This includes labels, review requests, reviews and their reactions, the pull
request and its reactions, comments and reactions, inline threads and replies,
remote commit and GitHub-signature evidence, effective commit checks, rulesets,
and branch protection. The two normalized observations must be identical. Their
connections, API calls, and items are recorded with a `.revalidation` suffix
and count against the same configured caps. Any
difference terminates with `BLOCKED_INCOMPLETE_REVIEW_STATE` before output is
prepared.

Independent cursors prevent unequal page counts from causing duplicate or
omitted reads. `completeness.fully_paginated_connections` records pages and
items for every completed connection. `completeness.api_calls` and
`completeness.items` record actual bounded work. Every paginated request uses a
page size of 100, and loaded evidence is rejected when its item count could not
fit within the recorded number of pages. This keeps recomputed digests from
legitimizing impossible, under-reported API-call evidence.

The configured defaults are 200 API calls, 10,000 aggregate items, 500 threads,
10,000 comments, and 10,000 reactions. Reaching a cap while `hasNextPage` is
true is never completeness. The helper terminates with
`BLOCKED_INCOMPLETE_REVIEW_STATE` and identifies the exact connection and
cursor. A nested-page failure prevents any authoritative snapshot or requested
output from being emitted.

There are no retries, sleeps, polls, or wait-until-complete loops. One failed or
timed-out API call is one terminal blocker.

## Signatures

Each PR commit records two independent observations:

1. GitHub's signature type, state, signer, and verification result;
2. local `git verify-commit --raw` evidence when the commit object exists,
   with the signature format derived from the commit's standard ASCII-armor
   header rather than potentially ambiguous verifier status text.

Valid SSH and OpenPGP signatures are accepted when configuration permits them.
The evidence distinguishes `valid`, `invalid`, `unsigned`, `unknown_key`,
`object_unavailable`, and `verification_pending`. An unknown key is never
reported as cryptographically verified. A `valid` state requires
`verified: true`; every other state requires `verified: false`. Required
invalid, unsigned, unknown, pending, unavailable, or internally inconsistent
verification blocks evidence verification, and therefore also blocks the
open-PR gate. The helper does not import keys or persist
signing configuration. Verification still uses the configured trust material,
while command-scoped overrides prevent configuration from substituting the
verifier executables themselves.

## Required checks

Requiredness is derived from the repository-rule and branch-protection sources
enabled by configuration. Disabled sources are not called. It is not derived
from a hard-coded workflow name or from visible green checks alone. Check runs
and status contexts retain stable GitHub identities and are matched to required
contexts plus application IDs when those IDs are governed. Gate verification
is preceded by evidence verification, which rebuilds requiredness and outcomes
from the supplied current policy rather than
trusting capture-time outcome labels. Enabled rulesets and branch protection
layer together: an application-specific branch-protection requirement cannot
erase a generic same-named ruleset requirement. Within branch-protection
evidence itself, the application-bound form still refines its legacy generic
context. The gate also retains each configured source's strict up-to-date
policy and blocks a `BEHIND` merge state whenever either enabled source requires
checks against the current base.

The anchor records GitHub's potential test-merge commit. When that commit has
any check or status context, its fully paginated rollup is authoritative;
otherwise the helper captures the head-commit rollup. The selected source and
OID are stored, semantically validated, and independently selected again during
revalidation. An open PR whose test merge is still being generated blocks as
incomplete instead of assuming the head rollup is authoritative. A generic
required name matches every check-run and legacy
status-context entry when both kinds are present, so one successful kind cannot
hide a failed same-named counterpart. It does not invent an absent context
kind; application-specific requirements remain bound to a check run from that
application.

Evidence distinguishes required success, pending, failure, and absence;
non-required success, pending, and failure; and unknown requiredness. Required
skipped checks follow the explicit `check_policy.expected_skipped` value.
GitHub's seven-day recency rule governs whether a check or expected application
can be selected when required-check policy is configured; it does not expire a
successful result on the current effective commit. A
missing or inaccessible configured rules source, unsupported check type,
malformed rule, required-workflow rule that cannot be mapped unambiguously to
the captured check rollup, or otherwise unknown requiredness terminates with
`BLOCKED_INCOMPLETE_REVIEW_STATE`. Pending checks are reported once and are not
polled. Effective-check state, applicable rules, and the derived required-check
evidence must also match their bounded revalidation observations.

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
retry loop, or execution of caller-selected helper programs. GitHub CLI calls
pin `GH_HOST` to `github.com` and pass `--hostname github.com` explicitly;
caller-provided host overrides and repository-context inference cannot redirect
evidence reads. GraphQL operations are static query documents with variables.
Git commands run with pagers pinned, optional locking disabled, replacement refs
ignored, lazy fetches disabled, and repository- or object-selection environment
overrides removed before process creation. Trace-file and executable-path
overrides are removed as part of the same boundary. Command-scoped Git
configuration disables filesystem-monitor hooks and pins every supported
signature-verifier program.

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

- `0` means the requested capture, render, evidence verification, or gate
  completed without its applicable mechanical blocker.
- `2` means invalid or unsafe local input or output handling.
- `3` means a deterministic state, API, completeness, signature, check, or
  review-state blocker.

Offline tests use fake `gh` and fake Git executables. They cover deterministic
serialization, outer and nested pagination with unequal page counts, reactions,
caps, partial failures, signature-envelope classification, update-time and
connection-count anchor races, strict stale-base state, required checks, hostile
rendering, atomic outputs, host pinning, merge-state policy coverage, commit-set
invariants, test-merge selection, duplicate-name check/status evaluation,
volatile-evidence revalidation, sanitized Git
environments, fsmonitor and verifier-program suppression, and executable-call
spies that reject GitHub and Git writes. Live acceptance is a separately
identified read-only phase and never requests an AI review.
