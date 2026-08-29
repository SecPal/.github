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
  safely dispositioned on the current pull-request head. For a tracked
  out-of-scope finding, it does not claim implementation or completion.
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

A `TRACKED_AS_FOLLOW_UP` target additionally receives one bounded canonical
work-graph read immediately before its mutation. This read is limited to the
exact follow-up identity authenticated by the signed eligibility digest.

Every apply invocation therefore performs three complete target reads per
thread before any mutation cost. Already-resolved targets are treated
idempotently and require no write, but receive the same two stable rechecks.
Target comments are cursor-paginated as needed. A dry run performs only the
initial read. The complete invocation shares the canonical repository
registry's API-call, review-thread, and comment limits. Before each write it
verifies that the remaining budgets cover every known target recheck and
mutation plus the unavoidable first API read for every later unresolved tracked
follow-up. It does not guess the cost of variable future graph traversal.

The authenticated late-disposition path performs two equal capture reads when
the detached artifact is created. At apply time it reads the named target once,
performs two equal preflight projections before any write, and performs two more
equal projections immediately before the exact mutation.

## Safety boundary

The command verifies only the invariants required for this operation:

- the CLI and supported programmatic entry point both consume the canonical
  reviewed-state, validation-attestation, repository, and eligibility inputs;
  caller-constructed evidence objects or self-computed matching digests cannot
  authorize mutation;
- repository and PR exist;
- repository is an exact entry in the canonical production registry;
- PR is open;
- current PR head equals the caller-provided expected current head OID;
- the reviewed-state file equals the caller-provided captured state digest;
- successful validation evidence binds that reviewed state to the exact
  verified fix commit through a final attestation and the signed commit's
  matching validation-receipt trailer; the signed receipt also authenticates
  the canonical eligibility-manifest digest;
- the local repository has the exact registered origin and expected `HEAD`, the
  commit tree equals the validated tree, and the commit has a locally verified
  accepted signature;
- a new fix commit has exactly the reviewed head as its parent and exactly one
  matching `SecPal-Validation-Receipt` trailer;
- the eligibility manifest binds the repository, PR, reviewed head,
  reviewed-state digest, and every requested thread exactly; each thread has an
  allowed classification/disposition, finding IDs, and evidence digest, and
  the complete canonical manifest must match the digest authenticated by the
  signed validation receipt;
- `OUTSIDE_PR_SCOPE + OUT_OF_SCOPE` is never eligible; the only out-of-scope
  resolution path is `TRACKED_AS_FOLLOW_UP` with one exact authenticated
  `repository`, positive `issue_number`, and matching canonical GitHub issue URL;
- immediately before that resolution, the canonical read-only work-graph layer
  proves the same follow-up remains accessible, open, and structurally complete;
  a blocked follow-up is allowed and does not become a prerequisite;
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
bindings are `repository`, `pull_request_number`, `reviewed_head_sha`, and
`reviewed_state_digest`. Create it after classification but before complete
validation. `attest-validation --eligibility-evidence` places its canonical
SHA-256 digest in the validation receipt, which the signed commit trailer and
final attestation authenticate. The resolver recalculates that digest and
rejects any post-validation classification, disposition, finding, or evidence
change before its first GitHub read.

For a typed two-parent Ready integration, supply the same eligibility artifact
alongside `--integration-evidence` during validation and binding. This emits
the closed version-1.2
`ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION`. Resolution then
also supplies `--integration-evidence`; the resolver uses the integration
verifier to authenticate the exact two parents, tree, receipt and integration
trailers, reviewed state, signer, and eligibility digest before applying the
ordinary exact-thread checks. Version-1.1 integration attestations do not carry
this authority and are rejected for resolution.

New manifests use schema version 1.1. The resolver also reads already-authenticated
version 1.0 manifests for the legacy resolution-eligible dispositions. It
authenticates the original version 1.0 canonical payload before normalizing the
missing `follow_up` value internally. Version 1.0 never accepts a `follow_up`
field or `TRACKED_AS_FOLLOW_UP`; tracked follow-up resolution requires version
1.1 and its exact non-null identity.

```json
{
  "schema_version": "1.1",
  "repository": "SecPal/api",
  "pull_request_number": 123,
  "reviewed_head_sha": "0123456789abcdef0123456789abcdef01234567",
  "reviewed_state_digest": "REVIEWED_STATE_SHA256",
  "eligible_threads": [
    {
      "thread_id": "PRRT_example",
      "classification": "VALID_ACTIONABLE",
      "disposition": "CORRECTED_AND_VERIFIED",
      "finding_ids": ["finding-1"],
      "evidence_digest": "FINDING_EVIDENCE_SHA256",
      "follow_up": null
    }
  ]
}
```

## Post-final-push late disposition

Commit-bound eligibility remains the normal remediation path. A distinct
resolution-only path exists only for exact technically non-blocking feedback
outside the authenticated final feedback boundary and observed on the unchanged
final delivery head. It does not extend the
delivery lifecycle, rerun validation, consume an unrestricted review or
remediation cycle, change the delivery tree, create a commit or push, inspect
CI, request review, mark Ready, or imply merge readiness.

The path first verifies the complete final reviewed state, canonical final
eligibility artifact, validation receipt, final attestation, local final tree
and head, receipt trailer, accepted commit signature, and exact origin. The
eligibility digest must match the receipt and attestation, every eligible thread
must exist in the reviewed snapshot, and the proposed late thread must be absent
from both final sets. Classification creation, disposition creation, and
resolution independently re-establish this origin predicate. It derives the
delivery signer fingerprint from
that cryptographic verification. It then captures only the one explicitly
named live thread and signs the canonical
[`late-classification.schema.json`](../.agents/skills/secpal-pr-review/references/late-classification.schema.json)
artifact. The disposition creator verifies that artifact and signature, checks
the exact live finding again, computes the classification digest internally,
and signs the canonical
[`late-disposition.schema.json`](../.agents/skills/secpal-pr-review/references/late-disposition.schema.json)
artifact with the OS-account signing configuration. The actual detached signer
must equal the final delivery signer; a signer identity declared by the
artifact is never its trust root. Artifact and signature outputs must be in the
private session area outside the delivery repository, so creating the evidence
cannot alter that worktree or tree.

The initial supported authorization is exactly
`INVALID_FALSE_OR_MISLEADING + DISPROVEN_WITH_EVIDENCE` with
`technically_blocking=false`. Classification is independently established and
recorded in separately signed exact evidence; no comment-text heuristic exists.
The signed artifact
binds the repository, delivery issue, PR, unchanged final head and tree, final
receipt/attestation/eligibility digests, signer, exact thread, top-level comment
node and database identities, finding-body digest, reply-state digest and
count, resolved/outdated states, classification evidence digest, disposition,
and exact resolution action. It never selects threads by query or pattern.

“Post-push” is lifecycle shorthand for this authenticated boundary. No GitHub
wall-clock push-order proof is used or claimed: authority comes from exact
absence in the authenticated final reviewed-state and commit-bound eligibility
artifacts while the delivery head remains unchanged.

Create authenticated classification evidence, then detached disposition
evidence:

```bash
python3 scripts/secpal-create-late-classification.py \
  --repo SecPal/api \
  --delivery-issue 456 \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --final-reviewed-state FINAL_REVIEWED_STATE.json \
  --expected-final-reviewed-state-digest FINAL_REVIEWED_STATE_SHA256 \
  --final-validation-evidence FINAL_ATTESTATION.json \
  --final-eligibility-evidence FINAL_ELIGIBILITY.json \
  --thread-id PRRT_example \
  --finding-id LF-LATE-1 \
  --finding-evidence-digest FINDING_EVIDENCE_SHA256 \
  --classification INVALID_FALSE_OR_MISLEADING \
  --disposition DISPROVEN_WITH_EVIDENCE \
  --technically-blocking false \
  --output SESSION/LATE_CLASSIFICATION.json \
  --signature-output SESSION/LATE_CLASSIFICATION.json.sig

python3 scripts/secpal-create-late-disposition.py \
  --repo SecPal/api \
  --delivery-issue 456 \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --final-reviewed-state FINAL_REVIEWED_STATE.json \
  --expected-final-reviewed-state-digest FINAL_REVIEWED_STATE_SHA256 \
  --final-validation-evidence FINAL_ATTESTATION.json \
  --final-eligibility-evidence FINAL_ELIGIBILITY.json \
  --classification-evidence LATE_CLASSIFICATION.json \
  --classification-signature LATE_CLASSIFICATION.json.sig \
  --output SESSION/LATE_DISPOSITION.json \
  --signature-output SESSION/LATE_DISPOSITION.json.sig
```

Resolve only the authenticated conversation:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --delivery-issue 456 \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head 0123456789abcdef0123456789abcdef01234567 \
  --reviewed-state FINAL_REVIEWED_STATE.json \
  --expected-reviewed-state-digest FINAL_REVIEWED_STATE_SHA256 \
  --validation-evidence FINAL_ATTESTATION.json \
  --final-eligibility-evidence FINAL_ELIGIBILITY.json \
  --late-classification-evidence SESSION/LATE_CLASSIFICATION.json \
  --late-classification-signature SESSION/LATE_CLASSIFICATION.json.sig \
  --late-disposition-evidence SESSION/LATE_DISPOSITION.json \
  --late-disposition-signature SESSION/LATE_DISPOSITION.json.sig \
  --thread-id PRRT_example \
  --apply
```

Commit-bound `--eligibility-evidence` and detached
`--late-disposition-evidence` are mutually exclusive. Missing, non-canonical,
duplicate-keyed, unknown-version, unsigned, corrupt, differently signed, or
rebound evidence fails before GitHub access. Any live head, PR, thread, comment,
body, reply, resolution, or outdated-state drift blocks before mutation.

## Operational rule

When the user explicitly asks to resolve comments that have been fixed and
pushed, use this simple path with the reviewed-state capture, its recorded
`state_digest`, and the successful validation evidence for the fix commit.
Also provide the exact local repository root and the eligibility manifest
created from the completed finding classifications and dispositions and
authenticated by the signed validation receipt.
Full review remediation also uses this path after its signed push. A raw
validation receipt for an unchanged head is not authenticated by that existing
commit and cannot authorize commit-bound resolution; do not create an
artificial commit to work around this boundary. Only an exact post-final-push
thread with separately authenticated late-disposition evidence may use the
resolution-only exception above. Do not route resolution through the readiness or
forensic workflow unless the current user instruction explicitly asks for CI
inspection, readiness, or merge authorization. Even then, the CI observation
is one bounded current-state read with no polling, waiting, sleeping, or
automatic repetition.
