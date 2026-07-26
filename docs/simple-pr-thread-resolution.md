<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Simple PR Thread Resolution

Use this path after review findings have already been evaluated, fixed where
necessary, validated once, committed, and pushed.

## Purpose

Thread resolution and merge readiness are different operations:

- **Thread resolution** records that a specific review conversation has been
  addressed on the current pull-request head.
- **Merge readiness** evaluates required checks, signatures, branch protection,
  mergeability, complete validation evidence, and any broader release policy.

The simple resolver keeps those concerns separate. It does not run tests, read
CI, classify reactions, compare unrelated PR feedback, create commits, push, or
make a merge decision.

GitHub-hosted CI may be inspected only when the current user instruction
explicitly requests CI status, check status, merge readiness, or merge
authorization. A push, PR creation, review-remediation request, previous
request, repository convention, or thread-resolution request does not provide
that authorization. Local validation and local push hooks remain required and
allowed.

## Normal cost

For each explicitly named review thread:

1. one direct GraphQL read containing its PR membership, PR state, head OID,
   resolved/outdated state, and canonical comment state;
2. one equivalent last-moment target read before each write;
3. one GraphQL resolution mutation for each explicitly named thread that is
   still open after that read.

Already-resolved targets are treated idempotently and require no write. Target
comments are cursor-paginated as needed. The complete invocation shares the
canonical repository registry's API-call, review-thread, and comment limits,
and verifies before the first write that the remaining budgets cover every
known target recheck and mutation.

## Safety boundary

The command verifies only the invariants required for this operation:

- repository and PR exist;
- repository is an exact entry in the canonical production registry;
- PR is open;
- current PR head equals the caller-provided expected current head OID;
- every requested thread belongs to that PR;
- every requested thread and its comment identities, body digests, and reply
  relationships match the supplied reviewed-state capture;
- PR state, head, resolved/outdated state, and canonical target-comment state
  produce two equal complete projections immediately before each mutation or
  successful already-resolved report;
- new, edited, deleted, repeated, or incompletely paginated target comments
  block the mutation;
- each mutation response confirms the exact requested thread as resolved;
- the trusted `gh` executable and sanitized command environment are used.

If a later target fails after an earlier resolution succeeds, the command stops
without retry, prints a structured report naming resolved, failed, and
unattempted targets, and exits nonzero.

It intentionally does **not** block resolution because of:

- pending or failed CI;
- PR-level or comment reactions;
- unrelated new comments or reviews;
- mergeability or branch-protection state;
- validation receipts or attestation files;
- an unclean local worktree;
- missing local repository access.

Those signals remain relevant to a later merge decision, not to recording that
an individual conversation has been addressed.

## Usage

Dry run:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --reviewed-state REVIEWED_STATE.json \
  --thread-id PRRT_example
```

Apply:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --reviewed-state REVIEWED_STATE.json \
  --thread-id PRRT_example \
  --apply
```

Repeat `--thread-id` to resolve several fixed threads in one invocation.

## Operational rule

When the user explicitly asks to resolve comments that have been fixed and
pushed, use this simple path with the reviewed-state capture for those findings.
Full review remediation also uses this path after its signed push or after
proving that a no-change remediation retained the already-pushed head. Do not
route resolution through the readiness or forensic workflow unless the current
user instruction explicitly asks for CI inspection, readiness, or merge
authorization. Even then, the CI observation is one bounded current-state read
with no polling, waiting, sleeping, or automatic repetition.
