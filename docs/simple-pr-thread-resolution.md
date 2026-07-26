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

## Normal cost

For a pull request with at most 100 review threads:

1. one GraphQL read containing the PR state, head OID, and review-thread IDs;
2. one GraphQL resolution mutation for each explicitly named thread that is
   still open.

Already-resolved targets are treated idempotently and require no write. A PR
with more than 100 threads is paginated only until all requested targets are
found.

## Safety boundary

The command verifies only the invariants required for this operation:

- repository and PR exist;
- PR is open;
- current PR head equals the caller-provided expected head;
- every requested thread belongs to that PR;
- each mutation response confirms the exact requested thread as resolved.

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
  --thread-id PRRT_example
```

Apply:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --thread-id PRRT_example \
  --apply
```

Repeat `--thread-id` to resolve several fixed threads in one invocation.

## Operational rule

When the user explicitly asks to resolve comments that have been fixed and
pushed, use this simple path. Do not route the request through the full
merge-readiness or forensic review workflow unless the user explicitly asks for
a readiness audit, forensic evidence, or merge authorization.
