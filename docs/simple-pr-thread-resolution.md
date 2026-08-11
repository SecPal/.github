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
make a merge decision. It requires already-produced successful validation
evidence bound to the exact fix commit; consuming that evidence is not a
readiness inspection.

GitHub-hosted CI may be inspected only when the current user instruction
explicitly requests CI status, check status, merge readiness, or merge
authorization. A push, PR creation, review-remediation request, previous
request, repository convention, or thread-resolution request does not provide
that authorization. Local validation and local push hooks remain required and
allowed.

## Normal cost

For each explicitly named review thread:

1. one initial complete GraphQL read containing its PR membership, PR state,
   head OID, resolved/outdated state, and canonical comment state;
2. two equivalent complete last-moment target projections before each write or
   successful already-resolved report;
3. one GraphQL resolution mutation for each explicitly named thread that is
   still open after those reads.

Every apply invocation therefore performs three complete target reads per
thread before any mutation cost. Already-resolved targets are treated
idempotently and require no write, but receive the same two stable rechecks.
Target comments are cursor-paginated as needed. A dry run performs only the
initial read. The complete invocation shares the canonical repository
registry's API-call, review-thread, and comment limits, and verifies before the
first write that the remaining budgets cover every known target recheck and
mutation.

## Safety boundary

The command verifies only the invariants required for this operation:

- repository and PR exist;
- repository is an exact entry in the canonical production registry;
- PR is open;
- current PR head equals the caller-provided expected current head OID;
- the reviewed-state file equals the caller-provided captured state digest;
- successful validation evidence binds that reviewed state to the exact
  verified fix commit: a receipt when the validated head is unchanged, or a
  final attestation when remediation created a new commit;
- the local repository has the exact registered origin and expected `HEAD`, the
  commit tree equals the validated tree, and the commit has a locally verified
  accepted signature;
- a new fix commit has exactly the reviewed head as its parent and exactly one
  matching `SecPal-Validation-Receipt` trailer;
- the eligibility manifest binds the repository, PR, expected head,
  reviewed-state digest, validation-evidence digest, and every requested thread
  exactly; each thread has an allowed classification/disposition, finding IDs,
  evidence digest, and matching fix commit;
- every requested thread belongs to that PR;
- every requested thread and its comment identities, body digests, reply
  relationships, and resolution state match the supplied reviewed-state
  capture;
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
- an unclean local worktree.

Those signals remain relevant to a later merge decision, not to recording that
an individual conversation has been addressed.

## Usage

Dry run:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --reviewed-state REVIEWED_STATE.json \
  --expected-reviewed-state-digest REVIEWED_STATE_SHA256 \
  --validation-evidence VALIDATION_EVIDENCE.json \
  --eligibility-evidence ELIGIBILITY_EVIDENCE.json \
  --thread-id PRRT_example
```

Apply:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --reviewed-state REVIEWED_STATE.json \
  --expected-reviewed-state-digest REVIEWED_STATE_SHA256 \
  --validation-evidence VALIDATION_EVIDENCE.json \
  --eligibility-evidence ELIGIBILITY_EVIDENCE.json \
  --thread-id PRRT_example \
  --apply
```

Repeat `--thread-id` to resolve several fixed threads in one invocation.
The ordered `eligible_threads` array in the eligibility manifest must list
those IDs in the same order and cover no additional thread. Its top-level
bindings are `repository`, `pull_request_number`, `expected_head`,
`reviewed_state_digest`, and `validation_evidence_digest`. The resolver
calculates and reports the canonical SHA-256 digest of the validated manifest;
the manifest does not self-certify a caller-provided digest.

```json
{
  "schema_version": "1.0",
  "repository": "SecPal/api",
  "pull_request_number": 123,
  "expected_head": "0123456789abcdef0123456789abcdef01234567",
  "reviewed_state_digest": "REVIEWED_STATE_SHA256",
  "validation_evidence_digest": "VALIDATION_EVIDENCE_SHA256",
  "eligible_threads": [
    {
      "thread_id": "PRRT_example",
      "classification": "VALID_ACTIONABLE",
      "disposition": "CORRECTED_AND_VERIFIED",
      "finding_ids": ["finding-1"],
      "evidence_digest": "FINDING_EVIDENCE_SHA256",
      "fix_commit_sha": "0123456789abcdef0123456789abcdef01234567"
    }
  ]
}
```

## Operational rule

When the user explicitly asks to resolve comments that have been fixed and
pushed, use this simple path with the reviewed-state capture, its recorded
`state_digest`, and the successful validation evidence for the fix commit.
Also provide the exact local repository root and the eligibility manifest
created from the completed finding classifications and dispositions.
Full review remediation also uses this path after its signed push or after
proving that a no-change remediation retained the already-pushed head. Do not
route resolution through the readiness or forensic workflow unless the current
user instruction explicitly asks for CI inspection, readiness, or merge
authorization. Even then, the CI observation is one bounded current-state read
with no polling, waiting, sleeping, or automatic repetition.
