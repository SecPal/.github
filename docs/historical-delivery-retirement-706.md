<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Exact historical delivery disposition: #705 / PR #706

This contract owns only the terminal disposition of the never-enrolled
`SecPal/.github` delivery #705 / PR #706. It consumes the
[canonical delivery lifecycle](work-graph-contract.md#53-delivery-pr-lifecycle),
[finite review authority](secpal-pr-review-workflow.md), and
[evidence architecture](evidence-architecture-contract.md). It grants no ordinary
historical-Ready exception and no permission to consume this capability during
the implementation delivery for #1183.

## Evidence and qualification

The maintained entry point is `scripts/secpal-historical-retirement.py` through
the constructed Actions owner. Every live entry requires freshly authenticated
protected-main tooling, including the new modules in the existing owner closure.
Candidate bytes cannot qualify, authorize, reserve or retire their own delivery.

Read-only `inspect --output <workspace-local-file>` independently captures the
exact original PR and delivery issue, complete bounded native source commits,
timeline, provider reviews, issue comments, threads and thread comments. Native
Link pagination must complete with one page below 100 items; GraphQL connections
must have complete counts and no next page. Larger or incomplete history is a
blocker rather than permission to omit evidence.

The source must remain head `4760603b6f23bbd652432e82d1c6dc193c93c467`,
tree `c4c750238cfc4338d20d240f9bfec6e481ac5587`, with sole ordered parent
`d56bd229c11848ac9231023cd49f1e968486c94e`. The maintained Git verifier checks
GitHub verification and the actual SSH key against accepted signer policy in an
isolated repository. Provider JSON alone cannot authenticate the local source.

Qualification preserves creation at `2026-08-22T21:53:28Z`, directly Ready,
with zero actual Draft-to-Ready transitions. This is `DRAFT_FIRST_VIOLATION`.
It preserves both Code review objects, both unresolved/non-outdated threads,
and the failed Security acquisition `IC_kwDOQFR1MM8AAAABQNbsGQ`. It authenticates
no successful Security completion. No receipt trailer is present, but historical
receipt issuance remains `ISSUANCE_UNKNOWN`.

The existing protected journal supplies authenticated absence of CURRENT,
native genesis and lifecycle-aware advancement. Full ancestry, live protection,
and the tip are verified through maintained readers. Absence is an observation,
never genesis permission. The native resolver supplies #705's sole #706 primary
claim, #1183's legitimate #1032 ownership, and #676's prerequisite #705.
Issue body, complete provider evidence, graph, protected main and journal absence
are read again to reject races. The signed proof retains the full bounded native
observations, source-signature binding and issue-contract digest.

Protected-main qualification may identify that #1183 is still awaiting its own
completion. Issuance and retirement additionally require #1183 completed and
Issue #705's native prerequisites satisfied. No issue closure is performed here.

## Separately authorized terminal retirement

`inspect` issues no authorization. A separately authorized operator may invoke
`authorize` with a unique `--authorization-id` and the exact
`--exact-human-intent` value:

```text
RETIRE_UNMERGED_SECPAL_GITHUB_705_PR_706_WITHOUT_SUCCESSOR_OR_REVIEW
```

Issuance recaptures the live proof and signs the closed, version-1.0
`SECPAL_HISTORICAL_RETIREMENT_AUTHORIZATION` using the existing transition role.
The intent expires within 900 seconds and binds the exact source, chronology,
contract, graph, accepted main and journal tip. A copied seal or caller-selected
observation cannot replace the live recapture. No new signer or credential is
provisioned. This command must never be inferred from #1183's implementation
authorization.

`retire --authorization <signed-file> --apply --output <file>` authenticates the
exact signed intent, expiry and independently recaptured proof. It reserves one
attempt by appending `SECPAL_HISTORICAL_RETIREMENT_CLAIM` in the existing protected
journal, using its existing publication role and exact predecessor CAS. The
claim embeds the signed intent and complete historical evidence; it selects no
CURRENT terminal and creates no genesis or lifecycle. Both journal readers use
one shared verifier, reject replay and reject any competing #705 lifecycle
admission, enrollment or recovery in the entire ancestry. Native initialization
for #705 also fails closed, regardless of a new PR number.

Only the invocation whose definite CAS and independent read-back succeed can
attempt the single exact GitHub `PATCH /repos/SecPal/.github/pulls/706` with
`state=closed`. Fresh source, graph, contract, operator and expiry checks follow
the reservation and precede that write. No issue, branch, review, thread, Draft
state or history write is exposed. The source branch is retained.

The write has distinct definite-success, authenticated HTTP-rejection and
ambiguous-transport outcomes. Every attempted write receives one bounded native
read-back. Verified retirement requires CLOSED, unmerged, exact preserved source
and provider evidence, exactly one native closure observation, the expected
operator, the unchanged open #705 contract, no remaining primary claim, the
unchanged #676 prerequisite, and the exact reservation reachable in protected
ancestry. Response success alone is insufficient.

A rejected or stranded attempt remains consumed. An uncertain CAS grants no
right to close, even if later found persisted. The result retains the attempted
claim OID and a bounded stage. After a partial or ambiguous result,
`reconcile --authorization <same-file> --claim-oid <exact-oid> --output <file>`
performs observation only. It never reserves, closes, retries, toggles or repairs
anything. Further failure requires a separate explicit decision. The original
evidence, both findings and Security failure are never rewritten or resolved.

## Successor and review-accounting disposition

`successor_eligibility` returns `eligible=false`, `authorized_successors=0`,
`review_authorized=false` and `enrollment_authorized=false`, with:

```text
NO_AUTHENTICATED_NON_RESETTING_FIRST_READY_AUTHORITY
```

Both historical provider objects remain observations of assessment; they prove
neither two canonical review cycles nor zero consumption. The full one-review
budget is conservatively reserved while canonical consumption provenance remains
unavailable. This reservation is a disposition fact, not a fabricated lifecycle
event, consumed-counter publication or successful review. Failed Security
acquisition remains failed, and findings remain unresolved.

Existing first-Ready authority cannot admit that reserved-review Draft baseline:
the adopted exception requires an actual authenticated historical Draft review.
The original directly-Ready assessment cannot supply one. Retirement alone,
missing publication, a new PR number, source correctness and green CI cannot
repair this missing authority. The implementation provides no successor creator
or review dispatch, and rejects fresh #705 native initialization rather than
silently resetting its counters.

At most one genuinely Draft successor could ever be considered, in this order:
verified terminal retirement; authenticated non-resetting accounting and lawful
first-Ready authority; separate exact human successor authorization; one Draft
successor; exact-source validation and native admission/enrollment; then separate
exact human assessment authorization and the canonical lifecycle/evidence gates.
That missing authority is not supplied by this contract. It must be independently
resolved before any successor creation. No recursive review, replacement chain,
fabricated event, automatic toggle or additional assessment entitlement is added.

## Architecture and permanent complexity

Observation uses the existing trusted GitHub transport, native resolver, signed
Git source verifier and protected journal readers. Native representation admission
is pure in `normalize_history`; successor disposition and write-result admission
are also pure. Signed-proof assembly consumes those facts. Execution composes the
maintained signing and CAS primitives with one exact state-only GitHub write.
These domains participate in one coherent terminal operation; their existing
invariant owners and trust boundaries remain authoritative.

Net permanent conceptual change: **one exact historical terminal-attempt
protocol**, represented by two domain-separated version-1.0 documents (intent
and reservation). There is no new journal, signer, trust root, lifecycle state,
counter, review budget, generic branch-write authority or generalized Ready
exemption. The fixed identity cannot be extended through caller configuration.
The reservation is permanent evidence; its consumption never resets.

Tests start from captured native #706 representations, exercise truthful
qualification and signed claims, reject substitution, hidden history, fabricated
events, receipt substitution, Security misrepresentation, counter resets,
replay, concurrent enrollment and partial writes, and preserve ordinary
Draft-first transitions. Tests and preliminary validation authorize no recovery.
Acceptance and independent read-only qualification from protected main must
precede any separately authorized target operation.
