<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Finite SecPal PR review contract

This is the normative Package-2.2 state and decision contract. It processes one
completed set of review feedback. It does not perform a review and does not
decide whether to request reviewers, request another round, or merge.

## User control and absolute limits

```yaml
normal_complete_snapshots: 0
normal_stable_feedback_reads: 1
normal_required_check_reads_before_resolution: 0
normal_complete_validation_runs: 1
maximum_holistic_audits: 1
normal_signed_remediation_commits: 1
normal_fast_forward_pushes: 1
maximum_evidence_replies_per_qualifying_invalid_finding: 1
maximum_evidence_replies_total: 10
maximum_intended_reactions_per_initial_logical_finding: 1
maximum_thread_resolutions_per_eligible_initial_thread: 1
review_requests: 0
draft_to_ready_transitions: 0
merge_operations: 0
auto_merge_operations: 0
```

The workflow issues zero review requests.
It issues zero Draft-to-Ready transitions.
It issues zero merge operations.
It issues zero auto-merge operations.
It has no polling and no sleep-and-retry. It has no recursive review loop, no
automatic rerun after a push, and no automatic request for new review.
A normal invocation has one remediation pass. Complete Package-2.1/2.2 snapshots
are available only in explicitly selected forensic/audit mode and are not a
normal-path prerequisite. The one normal stable-feedback read captures the
reviewed state before remediation. Pagination needed to finish that bounded
logical read does not create another read.

Security blockers stop immediately. A recoverable local error may be corrected
in the same invocation and reruns only its affected focused command. A
read-only transport or pagination failure may receive one bounded retry. A
mutation failure or unknown write result is never retried.

## Hosted CI authorization

Do not read, monitor, poll, wait for, summarize, or gate work on GitHub-hosted
CI unless the user explicitly requests CI inspection, check status, merge
readiness, or merge authorization in the current instruction.

A previous request, repository convention, push, PR creation,
review-remediation request, or thread-resolution request is not sufficient
authorization. Local validation and local push hooks remain required and
allowed. Push and PR creation do not authorize reading workflow runs, check
suites, commit statuses, Required Checks, CodeQL, GitHub Actions jobs,
mergeability, or merge readiness.

The default remediation path never performs a hosted-CI read. It never waits,
polls, sleeps, repeats a status read, keeps a run active for CI, or instructs
the user to start another run because a hosted check is pending.

## Simple resolution-only path

An explicit request only to resolve named review threads that have already been
evaluated, fixed where necessary, validated, committed, and pushed uses
`scripts/secpal-resolve-fixed-threads.py` instead of the normal remediation
state machine.

This path requires the exact repository, pull request number, expected current
head OID, reviewed-state file, caller-captured reviewed-state digest, and
successful validation evidence bound to the verified fix commit, local
repository root, and per-thread eligibility evidence, plus thread IDs. It
verifies the registered origin, local head, validated tree, accepted local
commit signature, and, for a new fix commit, the sole parent and validation
receipt trailer before any GitHub read. The receipt and final attestation must
authenticate the canonical eligibility-manifest digest. It also requires the
eligibility manifest to cover the requested threads exactly and bind their allowed
classifications/dispositions, finding IDs, evidence digests, reviewed head, and
reviewed-state digest.
The CLI and supported programmatic mutation entry point consume those canonical
artifacts and independently verify the same complete chain before any GitHub
read. Caller-constructed evidence objects and caller-computed matching digests
are not mutation authorization. Target-processing logic is reached only after
the reviewed-state, attestation, signed-commit, receipt-trailer, and eligibility
bindings have all been verified.
New evidence uses schema version 1.1. Immutable authenticated version 1.0
evidence remains readable only for the legacy resolution-eligible dispositions
and is authenticated in its original canonical form before internal
normalization. Version 1.0 cannot carry `follow_up` or authorize
`TRACKED_AS_FOLLOW_UP`; those semantics require version 1.1.
It then reads every named target
completely, and requires its comment
identities, body digests, reply relationships, and resolution state to match the
feedback that was actually classified. It then verifies PR membership and
records current resolved/outdated state. Immediately before each write or
successful already-resolved report, it performs two more equal complete target
projections, rechecks the open PR and expected head, and verifies the exact
target state. It then verifies that a mutation response
identifies the requested resolved thread. A changed head, closed PR, missing
target, reviewed-state mismatch, unstable projection, or externally changed
target blocks the next write. Only repositories in the canonical production
registry are accepted. The registry's API-call, review-thread, and comment
limits bound the complete invocation, and the helper resolves `gh` through the
accepted trusted executable and environment boundary. Before each write, it
verifies that the remaining budgets cover the minimum known cost of every
stable target recheck and mutation plus the unavoidable first API read for
every later unresolved tracked follow-up. Variable work-graph traversal growth
remains bounded by the same shared budget and may still produce a structured
partial failure when that growth was not knowable before an earlier write.

Duplicate or malformed direct-call inputs fail before the first read. If a
later target fails after an earlier resolution succeeded, the helper stops
without retry, emits one structured report naming resolved, failed, and
unattempted targets, and exits nonzero.

The resolution-only path performs no feedback classification, validation,
attestation creation, commit, push, Required Check read, readiness audit, review
request, or merge operation. It consumes already-produced validation evidence
only. It is also the default post-push resolution step after
feedback remediation. It is not selected for a separately requested readiness
audit, forensic evidence capture, or merge evaluation.

## Normal fast-path state machine

```text
INITIALIZE
  → READ_STABLE_FEEDBACK_ONCE
  → CLASSIFY_AND_FIX_ALL_CURRENT_FINDINGS
  → FOCUSED_VALIDATION_WHILE_EDITING
  → HOLISTIC_AUDIT
  → COMPLETE_LOCAL_VALIDATION_ONCE
  → IF_TRACKED_TREE_CHANGED
      → SIGNED_COMMIT
      → PUSH_ONCE
      → RESOLVE_FIXED_THREADS
      → STOP
    ELSE_VERIFY_UNCHANGED_HEAD
      → STOP_WITHOUT_THREAD_RESOLUTION
```

A security blocker terminates at the state that detects it. A recoverable local
error does not advance the state or consume a remediation cycle. When
remediation changes no tracked source file and every finding is safely disposed,
the invocation does not create an artificial commit: it verifies the unchanged
local, remote, and PR head, stops without thread resolution because the raw
receipt is not authenticated by that existing commit, and reports the retained
dispositions.

### State rules

`INITIALIZE` requires explicit invocation, loads the registry, creates private
session storage, initializes counters, and performs no GitHub write.

`READ_STABLE_FEEDBACK_ONCE` captures repository/PR/head/base identity, reviews,
top-level comments, threads, thread comments, body digests, resolved/outdated
state, reactions, and actors under the explicitly selected registry entry. It
excludes Required Check results and all other volatile readiness values.

`CLASSIFY_AND_FIX_ALL_CURRENT_FINDINGS` independently proves each classification,
adds failing regression coverage for valid findings, and implements the smallest
coherent correction. `FOCUSED_VALIDATION_WHILE_EDITING` runs only affected tests.
Focused validation must not invoke a complete, repository-wide, or aggregate suite
by default, directly or through a wrapper. When the relevant regression is
available only through such a suite, isolate the smallest direct test, filter,
or fixture first. A registered focused-only command explicitly authorized by
its matching manual gate is the bounded exception. It remains excluded from
unconditional complete validation.

`HOLISTIC_AUDIT` runs once and covers correctness, security, privacy, data
integrity, lifecycle, rollout, user control, and avoidable complexity. All
source, provenance, edge-case, and diff inspection finishes in this state.

`COMPLETE_LOCAL_VALIDATION_ONCE` runs the registry's unconditional focused
commands and every required local command once and returns a deterministic
receipt binding repository, parent head,
staged-tree SHA, registry digest, command-set digest, successful result, and
reviewed-feedback digests plus explicit satisfied evidence for every registered
manual gate and the canonical digest of the finalized eligibility manifest.
The manifest is finalized after classification and before this state; it binds
the reviewed head/state and every eligible thread's classification,
disposition, finding IDs, and evidence digest without referring to the not-yet-
created fix commit. On entry, the tracked tree, eligibility manifest, and
holistic-audit result are frozen; independent discovery and audit do not
continue in or after this state. A failed command produces no receipt; the
command invalidates any report already at its
configured output before validation begins, terminates this invocation, and
permits no tree change or complete-command retry. A new explicit remediation
invocation must capture fresh state and audit any correction before its single
complete validation. A successful complete validation is never repeated. Time
is informational only and cannot determine validity.

`IF_TRACKED_TREE_CHANGED` selects only between the proven staged tree and the
reviewed tree. When remediation changes no tracked source file, it takes
`ELSE_VERIFY_UNCHANGED_HEAD`, proves local, remote, and PR heads still equal the
reviewed head, and skips `SIGNED_COMMIT` and `PUSH_ONCE`. The resulting raw
receipt is not authenticated by the already-existing commit and cannot
authorize thread resolution. The workflow stops without resolution rather than
creating an artificial commit or trusting self-hashed evidence.

`SIGNED_COMMIT` creates one cryptographically
signed commit with the receipt digest as its single
`SecPal-Validation-Receipt` trailer and proves that its sole parent, tree, and
signed trailer exactly match the receipt. It then returns the final head-bound
attestation without rerunning validation. This pre-push bind verifies the local
signature and configured format only.
`PUSH_ONCE` proves the remote branch still has the expected predecessor and
makes one ordinary push. Neither state amends, rebases, force-pushes, bypasses
hooks, or uses administrator authority. After the push it verifies only local,
remote, and PR head equality.

`RESOLVE_FIXED_THREADS` invokes `scripts/secpal-resolve-fixed-threads.py` for
the exact eligible thread IDs, current head, reviewed-state file and captured
digest, successful validation evidence bound to the verified fix commit, local
commit proof, and exact per-thread eligibility evidence authenticated by the
signed validation receipt. Resolution depends
only on those inputs, the open PR, exact head, target
membership, equality with the
reviewed target-comment identities and digests, two equal complete current
target projections, and exact mutation response. It does not read or depend on
hosted CI, Required Checks, CodeQL, mergeability, branch protection, PR
reactions, unrelated feedback, or worktree cleanliness.

Only the final attestation for a new signed fix commit is accepted as validation
evidence. A raw validation receipt for an unchanged head has no receipt trailer
in that pre-existing commit and fails closed before any GitHub read.

`STOP` reports the commit, branch, remote synchronization, local validation,
worktree state, PR identity, and resolution results. The workflow never merges;
merge remains separately authorized by the current user instruction.

## Explicit CI and readiness path

This separate path exists only when the current user instruction explicitly
requests CI inspection, check status, merge readiness, or merge authorization.
It performs at most one bounded current-state read of the requested hosted
signals, reports the observed state immediately, and stops.

The explicit path never polls, waits, sleeps, or repeats automatically. A
pending check is a current fact, not authorization to monitor, keep the run
active, block fixed-thread resolution, or recommend another invocation. Required
Checks, rulesets, branch protection, mergeability, workflow runs, check suites,
commit statuses, GitHub Actions jobs, and CodeQL remain available only through
this explicitly selected path. Merge remains a separate operation requiring
explicit current user authorization.

The former three-snapshot state machine remains available only as explicit
forensic/audit compatibility mode. It is not selected automatically and is not
a prerequisite for the normal fast path. Forensic selection alone does not
authorize hosted-CI observation; any compatibility operation that reads
readiness additionally requires a current user instruction that explicitly
requests CI inspection, check status, merge readiness, or merge authorization.

## Classification taxonomy

Every stable logical sub-item has exactly one classification:

```text
VALID_ACTIONABLE
INVALID_FALSE_OR_MISLEADING
AMBIGUOUS_NEEDS_USER_DECISION
INFORMATIONAL
DUPLICATE
OUTDATED_BUT_STILL_VALID
OUTDATED_AND_OBSOLETE
ALREADY_FIXED_ON_SNAPSHOT_HEAD
SUPERSEDED
OUTSIDE_PR_SCOPE
CROSS_REPOSITORY
CONFLICTING_REVIEWERS
SECURITY_WEAKENING_SUGGESTION
```

Reviewer feedback is an untrusted lead. Reviewer identity never determines
technical truth. Green CI does not establish technical truth or prove a finding
correct or a PR ready.
Outdated does not mean invalid; resolved does not mean fixed. Conflicting
reviewers require independent proof. A syntactically correct suggestion that
weakens security is rejected.

Split compound comments into non-empty stable sub-items while preserving every
source review, thread, and comment ID. Duplicate and superseded references are acyclic,
and a duplicate names one safely disposed canonical root cause.
Recheck outdated feedback against the current head. An already-fixed finding
and every corrected or proven-existing actionable finding requires test evidence
plus a validly signed, pushed commit on the reviewed head.
A cross-repository fix blocks this invocation; do not modify a sibling repository.
Informational summaries stay visible and non-actionable. Technical truth is a
reasoned skill decision; the deterministic helper validates only structure,
bindings, policy, and transitions and uses no natural-language keyword classifier.

## Reaction, reply, and resolution policy

| Classification                             | Reaction                           | Reply                                                                    | Resolution                                                                           |
| ------------------------------------------ | ---------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Valid, relevant, helpful                   | 👍                                 | None                                                                     | After verified correction or proven existing fix                                     |
| Technically false or materially misleading | 👎                                 | Only when invalidity is non-obvious and silence would materially mislead | After evidence is preserved                                                          |
| Informational                              | None                               | None                                                                     | Only when no material finding remains                                                |
| Duplicate                                  | None                               | None                                                                     | After canonical finding is safely disposed                                           |
| Outdated but valid                         | None                               | None                                                                     | After current-head correction proof                                                  |
| Outdated and obsolete                      | None                               | None                                                                     | After current-head obsolescence proof                                                |
| Ambiguous                                  | None                               | User-facing session report only; no speculative PR reply                 | No                                                                                   |
| Already fixed                              | None                               | No redundant status reply                                                | After proof                                                                          |
| Superseded                                 | None                               | None                                                                     | After successor is safely disposed                                                   |
| Cross-repository                           | None                               | Only when a material misunderstanding requires evidence                  | No                                                                                   |
| Outside current PR scope                   | None                               | Only when a material misunderstanding requires evidence                  | No for `OUT_OF_SCOPE`; after authenticated tracking proof for `TRACKED_AS_FOLLOW_UP` |
| Security-weakening suggestion              | 👎 only when materially misleading | Evidence reply only when needed                                          | After evidence is retained                                                           |

Before a reaction, read the complete bounded target-reaction set, treat the exact
intended writer reaction as already applied, and block every other delta from
the snapshot. Never remove another actor's reaction. Before a reply, search the
complete bounded thread, treat the exact intended evidence reply as already
applied only when its parent comment, body, and writer all match, and block every
other delta. Never post “fixed,” “addressed,” commit-SHA status, or progress
messages. Before a legacy forensic reaction or reply, re-read PR-wide feedback
and block every delta except an exact intended or individually recorded policy write. A pending
reaction or reply must also fit within the effective post-write feedback caps;
an exact already-applied write consumes no additional reservation. Before
resolution, also re-read the target thread and refuse a resolved or changed
target. Default remediation uses the simple fixed-thread resolver, which reads
only each named target initially and immediately before its write.

`OUTSIDE_PR_SCOPE` remains the technical classification. `OUT_OF_SCOPE` means
only that the finding is outside the current PR and is never resolution-eligible.
The distinct `TRACKED_AS_FOLLOW_UP` disposition is permitted only for a material
`OUTSIDE_PR_SCOPE` finding whose review judgment establishes that the current PR
does not implement it and one canonical follow-up owns it. That disposition
binds exactly `repository`, positive `issue_number`, and the matching canonical
`https://github.com/owner/repo/issues/number` URL into the finding and eligibility
digests. Immediately before resolution, the guarded resolver uses the canonical
read-only work-graph implementation to prove the same issue is accessible, open,
and structurally complete. A blocked follow-up remains valid tracking; it need
not be `READY`, started, or complete. Missing, inaccessible, closed, malformed,
mismatched, or structurally incomplete evidence fails closed. Resolution records
safe disposition into that issue and never claims the follow-up was fixed,
implemented, verified, or completed.
The legacy mutation plan and fast-path batch schemas carry the same identity so
they cannot drop or reinterpret it, but they do not consume the signed
eligibility manifest and therefore cannot perform this new mutation. Tracked
follow-up resolution is routed through the simple resolver, which authenticates
that manifest through the receipt, signed commit trailer, and attestation.

## Stable feedback, readiness, attestation, and batch contract

Stable feedback is one canonical representation containing repository and PR
identity, the bound reviewed head and base branch/SHA, review IDs, top-level comment IDs and body
digests, review-thread and comment IDs and body digests, resolved/outdated state,
stable reactions, and source actors. PR-level `EYES` reactions are transient
activity markers and are excluded before canonicalization; nested `EYES`
reactions and every other reaction remain stable feedback. Its feedback digest excludes the head solely so a
validation attestation can authorize the expected reviewed-head-to-remediation-
head transition; the state digest includes the head and base. It contains no
Required Check, mergeability, worktree, signature, or validation result.

Explicitly requested volatile readiness separately contains the current PR
head, registered default branch and allowed base repository, base SHA, local and
remote heads, clean-worktree result, Required Checks, mergeability, GitHub
merge-state status, strict-base policy, authenticated actor, signature
classifications, signed validation-receipt trailer, and validation-attestation
identity. It is read at most once only under the explicit CI and readiness path.

A validation receipt is produced by the single complete run and binds its staged
tree, canonical eligibility-manifest digest, and normalized satisfied evidence
for every registered manual gate. After
the signed commit, that receipt may be bound once only when the commit's parent,
tree, and single `SecPal-Validation-Receipt` trailer match exactly. The final
validation attestation contains at least `repository`, `head_sha`,
`registry_digest`, `command_set_digest`, `successful_result`, validated tree,
receipt digest, manual-gate evidence, and authenticated eligibility digest. It
also binds the reviewed state and
feedback digests. The batch independently reconstructs the receipt from the
live signed commit and rejects a caller-authored attestation file that lacks the
matching signed trailer. Canonical JSON and SHA-256 make it deterministic;
timestamps do not participate. Any bound-value change invalidates the
attestation. It contains no environment dump, command output, credential, or
secret. Manual-gate evidence and every user-controlled batch string are rejected
when they contain the same secret-like patterns prohibited in forensic plans.

The sole-parent rule above remains authoritative for remediation and recovery.
`attest-validation --integration-evidence` is the distinct, explicitly selected
exception for one already-authorized Ready-PR integration candidate. Its closed
version-1.1 evidence kind is `TWO_PARENT_READY_INTEGRATION`; it requires explicit
delivery-issue, authorization-ID, and signer selectors and authenticates the
repository, PR, prior Ready head, live current registered default-branch tip,
exact ordered parents `[prior Ready head, authorized base head]`, combined tree,
stable-feedback digests, registered validation execution, accepted signer, and
finite lifecycle continuity. The candidate also carries exactly one signed
`SecPal-Integration-Evidence` digest trailer in addition to its validation-
receipt trailer. The final integration attestation binds both trailers, the new
head, ordered parents, validated and mechanical tree identities, and the exact
raw tree delta allowed for manual conflict resolution. A clean merge requires
exit status zero and an empty conflict set and delta. Exit status one is
conflict-bearing evidence: the exact sorted conflict paths are authenticated,
every path must be explicitly changed or deleted in the candidate, no other
path may change, and retained text conflict markers fail closed.

Parent 1 and its Ready/lifecycle claims are not caller assertions. A distinct
closed `READY_INTEGRATION_PRIOR_AUTHORITY` manifest binds the prior delivery
tree, receipt, final attestation, accepted signer, lifecycle identity, current
published authority digest, exceptional-history counters, and Ready-without-
transition state. The helper independently verifies that
ordinary delivery chain and a signed annotated authority tag whose trailer
binds the manifest digest. The prior commit trailer, reconstructed ordinary
receipt, final attestation, and prior-authority receipt identity must all agree.
Receipt reconstruction uses the validation registry committed in the immutable
prior delivery head, so a later independently delivered registry extension
cannot invalidate authentic historical delivery evidence.
It also consumes the maintained #750/#752 publication verifier and requires the
protected journal's current entry for the delivery to match the manifest's
publication object, publication digest, persistent lifecycle identity, current
head, finite counters, proof mode, and unused exceptional-continuation budget.
The mutable tag ref is resolved once to an authenticated annotated-tag object
OID; target, signature, signer, trailer, and diagnostics thereafter use only
that immutable object. OpenPGP authority matching distinguishes the verified
signing-subkey fingerprint from its authenticated primary-key fingerprint.
Integration evidence and its fresh receipt bind the same authority and tag-
object identities. During receipt creation, one trusted GitHub read must
also prove that the open Ready PR still has parent 1 as its head and that its
registered default branch currently resolves to parent 2. The pull request's
creation-time base OID is not a current-tip authority. Missing authority,
live-ref drift, or an unavailable observation fails closed without retry.

This integration topology consumes no unrestricted review or remediation cycle,
does not create Cycle 3, requests no review, and preserves `Draft=false` and
`Ready=true` without a transition. Unknown versions, ambiguous fields, generic
merge commits, reordered or substituted parents, base-ref drift, unlisted tree
delta, stale evidence, and signer substitution fail closed. The helper only
authenticates an already created candidate: it performs no branch integration,
push, Ready transition, hosted-check observation, or merge automation. A push
requires a separate fresh head-bound readiness evidence phase.

After an authenticated `BLOCKED_CYCLE_LIMIT_REACHED`, no normal Cycle 3 exists.
Only a separate, explicit user authorization may select
`attest-validation --exceptional-recovery-evidence`. Its closed
`READY_EXCEPTIONAL_RECOVERY` artifact binds repository, issue, PR, prior Ready
head/tree, recovery tree, exact reviewed-state and eligibility digests, exact
finding/thread identities, `review=1/1`, `remediation=2/2`, `Cycle 3=false`,
`Draft=false`, `Ready=true`, no Ready transition, and exceptional-recovery
count one. Its digest is carried by the ordinary single-parent receipt and
final attestation. It neither resets counters nor creates a reusable recovery
or recursive review path.

An explicitly requested readiness batch validates against
`fast-path-batch.schema.json`. It binds one
repository, PR, expected head, reviewed base branch/SHA, actor, reviewed digests, authorization digest,
classified findings, and a unique ordered set of eligible `THREAD_RESOLUTION`
operations. Each finding binds typed stable-feedback source identities/digests,
an optional unresolved thread, optional compound-source sub-item identity, classification,
classification-compatible disposition, evidence digest, and a follow-up identity
that is non-null only for `TRACKED_AS_FOLLOW_UP`. Fixed findings
also bind the signed validation-receipt digest as test evidence and a PR-commit
digest. Operations name their threaded findings instead of trusting a
free-standing disposition. Every top-level review/comment and its reactions,
stable pull-request reaction, unresolved reviewed thread, and comment/reaction in it has classification coverage
before the first live read. Preflight
and every logical read may retry once only for an unambiguous transient read
failure. Writes never retry. A partial failure records all applied operations,
the exact failed operation, and all later blocked operations, then stops.
Caller-supplied prior-result evidence is rejected because a post-mutation local
report has no signed trust root. Applied/failed/blocked target entries remain in
reports for audit and manual recovery only; an external resolution or other
stable-feedback delta blocks before the first write.
An explicit report output is initialized before the first write. If final
persistence fails after a mutation, the helper stops and emits the complete
in-memory applied/failed/blocked evidence to standard error for manual recovery.

User-authored commits are verified locally and must satisfy the configured SSH
or OpenPGP signing policy. When `require_github_verified` is enabled, they must
also have GitHub verification metadata with `verified = true` and
`reason = valid`. GitHub-generated web, squash, and merge commits use that
GitHub verification metadata. Missing local GitHub GPG key material is
`UNKNOWN_LOCAL_KEY`, not an invalid signature, and does not require key import.
Each commit is classified once per invocation.

## Forensic mutation-plan and action-helper contract

The authoritative validator dispatches on the original mutation-plan schema
version before semantic validation. Exact version 1.0 plans retain their
historical shape and legacy dispositions without a `follow_up` field. Exact
version 1.1 plans require the current `follow_up` shape and are the only plans
that may represent `TRACKED_AS_FOLLOW_UP`. Unknown versions, mixed shapes,
version 1.0 follow-up fields, and version 1.0 tracked dispositions fail closed.
Persisted version 1.0 session counters, replies, reactions, resolutions, and
returned mutation identities remain authoritative and are not rewritten before
their original shape is validated.

The schema-bound plan contains its version, repository, PR, immutable snapshot
digest, expected head, creation state, cycle, finite session counters, stable
logical findings, manual-gate evidence, and operations. Every operation contains an ID, one of
`REACTION`, `EVIDENCE_REPLY`, or `THREAD_RESOLUTION`, exact target node/database
and parent-thread IDs, expected current target state, expected authenticated
writer identity, expected immutable source actor identity, classification,
evidence digest, operation payload, returned mutation identity when already
applied, and any resolution preconditions.

Current target reads retain the exact node and database IDs of every reply
parent. Reply idempotency must match that node identity in addition to the body
and authenticated writer; database-ID-only or body-only attribution is invalid.

Each mutation target must be one of its logical finding's immutable source items,
or that finding's exact parent thread for a resolution. Its database ID, parent
thread, source actor, body digest, resolved state, and outdated state must match
the same snapshot item rather than unrelated values that merely occur elsewhere
in the snapshot. A source actor may retain the Package 2.1 all-null identity for
a deleted account; the authenticated writer identity remains complete and
non-null.

Pull-request-level reactions are schema-addressable classification sources but
are not mutation targets. Each such reaction in the immutable initial snapshot
requires its own safely disposed finding before resolution.
Reactions nested under reviews, conversation comments, and inline review
comments are likewise independent classification sources and require their own
safely disposed findings.
Every immutable initial-snapshot source item, and no later source, is covered
before any policy write. An unsplit source occurs in exactly one logical
finding; a compound source may occur in multiple findings only when each uses a
unique non-empty `source_subitem_id`. A reaction is never folded into its parent
comment's classification, and duplicate source/sub-item anchors are rejected.
Final-snapshot coverage may additionally contain an earlier policy write only
when its recorded identity, target, payload, parent thread, and authenticated
writer exactly match the operation that produced it. Such writes satisfy final
coverage but never become classification sources.

Plans are deterministic, secret-free, and bound to the exact repository, PR,
snapshot digest, and expected head SHA. A changed head invalidates a plan.
Every operation repeats the exact classification and evidence digest of its
named logical finding; evidence from another finding cannot authorize it.
The session state is one exact state-machine value. Every pending operation is
bound to its matching mutation phase, and terminal or unrelated phases cannot
enter mutation preflight. Mutation-capable phases also require their exact
counter state, so a later session cannot be relabeled as an earlier phase.
The helper independently verifies the supplied Package 2.1 evidence and refuses
every operation when that evidence or the plan's finite session already records
a terminal blocker.
Prohibited kinds are review request, Ready transition, label, issue, review
submission, merge, auto-merge, comment deletion, review dismissal, and branch
write.

The forensic compatibility surface retains only `inspect-actor`, `validate-plan`,
`react`, `reply`, and `resolve`; the normal surface adds only
`attest-validation` and `resolve-batch`. Every mutation command requires the
plan, operation ID, exact repository, PR, digest,
head, and explicit `--apply`. Without `--apply`, it performs no mutation. There
is no generic API passthrough. The helper uses argument arrays, an exact endpoint
and GraphQL-document allowlist, a pinned host, no shell, no Git write, no retry,
no polling, and no sleep. It reads target state first, verifies actor, target,
head, and idempotency, applies at most once, and reports the returned identity.
Registered local validation uses direct argument arrays and rejects shells,
executable-dispatch wrappers, and inline interpreter code by permitting only the
required direct tools, checked-in scripts, and approved project-script forms.
Later-state plans retain identities for earlier authorized writes and increment
the corresponding consumed counter exactly once. Before each new write, the
helper re-reads every earlier retained reaction, reply, and thread resolution
identity from live state before trusting it. It then compares one bounded,
canonical PR-wide feedback projection before every new write; every other new
or changed comment, review, thread state, reply, or reaction is late feedback.
Each live feedback check captures two complete cursor-paginated projections
within one shared API-call budget and requires canonical equality. During each
projection, pull-request anchors, pull-request reactions, and every connection
that already completed are also re-compared on later pages. A change to any
earlier page therefore fails closed.

## Forensic remediation-resolution readiness

Resolution is not inferred from the open merge gate. The final evidence must
independently prove all of the following:

- expected head unchanged and local, upstream remote, and PR heads equal;
- clean worktree and every relevant commit validly signed;
- selected focused and complete required local validation successful;
- all required checks successful, with no missing, pending, failed, or unknown
  required evidence;
- complete snapshot evidence and an unchanged expected target thread belonging
  to the immutable initial snapshot;
- the target remains unresolved and its classification permits resolution;
- every valid logical finding associated with it is corrected or disproven;
- every other unresolved target thread has complete classification/disposition;
- every material top-level finding has a resolvable disposition;
- no new feedback after the immutable snapshot;
- explicit satisfied evidence for every repository-registered manual gate;
- no head movement beyond the verified signed remediation descendant or other
  unsafe GitHub state; and
- no counter limit exceeded.

A no-push session requires identical initial and final heads and commit lists.
A remediation session requires exactly one new linear commit per recorded
signed commit and fast-forward push, with the chain starting at the immutable
initial head and ending at the expected final head. Reusing the final snapshot
as the initial anchor therefore fails closed.

Immediately before each forensic resolution write, the helper runs the
repository's unconditional focused and required local validation commands
without a shell and
performs one bounded live PR-wide feedback read. It compares the canonical
reviews, conversation comments, review threads, inline comments, and reactions
with the final snapshot, allowing only individually recorded earlier thread
resolutions, and separately compares the complete live target-thread comment
set with that snapshot. Top-level review, conversation-comment, and thread
connections are cursor-paginated within the registered API and item caps; a
missing, repeated, or non-advancing cursor fails closed.
After local validation and the initial final-feedback comparison, the helper
re-reads applicable rulesets, branch-protection required checks, the current
base identity/OID, test-merge/head check target, and every required-check
outcome within the same registered caps. Rules and check contexts each require
two equal complete projections, including all paginated pages. It then repeats
the bounded PR-wide feedback comparison and exact target-thread read immediately
before the resolution mutation. Any rule drift, feedback drift, target drift,
partial response, missing check, or non-successful required outcome blocks the
write.
The aggregate registry budgets of 200 recorded comments and 50 recorded
reactions include Package 2.1's mandatory second observation. Their effective
live limits of 100 comments and 25 reactions stay within every unpaginated
nested connection, so accepted evidence remains structurally re-readable.

Resolution remains read-only until one individual operation is explicitly
applied. An already-resolved target is accepted only when the plan records the
matching prior resolution identity; every unrecorded resolved or otherwise
changed target is blocked. The resolution plan's `pushed` precondition is true
exactly when the finite session records a fast-forward remediation push. A
no-remediation resolution therefore records `pushed: false` while retaining all
other readiness evidence.

## Terminal outcomes

“Prior policy writes” below means only individually authorized reactions or
exception evidence replies performed before the blocker; no write is allowed
after detection.

| Outcome                                   | Exact detection                                                                                                                             | Permitted prior writes                                                     | Required report                                                                        | Fresh invocation?                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `NO_ACTIONABLE_FINDINGS`                  | Every stable reviewed item is classified and none requires correction or user decision; technical evidence is complete                      | Classification-policy writes only                                          | Stable-state/head anchors, all dispositions, and counters                              | No; only if the user later chooses to process new feedback                    |
| `READY_FOR_USER_AUTHORIZED_SQUASH_MERGE`  | All technical, local, signature, push, final-state, CI, and thread-disposition proofs succeed; readiness is not based on CI alone           | Policy writes and eligible resolutions                                     | Full readiness evidence and explicit merge checkpoint                                  | No; wait for the user's separate merge decision                               |
| `NOT_READY_FOR_MERGE`                     | No more specific blocker applies, but complete readiness proof is absent                                                                    | Prior policy writes                                                        | Missing readiness evidence and current anchors                                         | Yes for any renewed processing                                                |
| `BLOCKED_UNCLEAN_WORKTREE`                | Worktree is not clean at entry or a required cleanliness check                                                                              | None when found at entry; otherwise prior policy writes                    | Exact status paths without changing them                                               | Yes after the user restores/accepts state                                     |
| `BLOCKED_HEAD_MOVED`                      | Local, remote, or PR head differs from the expected anchor at any check                                                                     | None before feedback capture; otherwise prior policy writes                | Expected and observed OIDs and detection state                                         | Yes                                                                           |
| `BLOCKED_UNEXPLAINED_COMMIT`              | Exact PR commit set contains a commit not explained by the reviewed session                                                                 | None                                                                       | Commit OIDs and why provenance is unexplained                                          | Yes after user decision                                                       |
| `BLOCKED_INVALID_SIGNATURE`               | A user commit lacks required local SSH/OpenPGP or GitHub verification, or GitHub-generated commits lack valid GitHub verification metadata. | No correction/push/resolution; prior policy writes possible if found later | Commit source and selected verification evidence                                       | Yes after new signed history is user-authorized; never amend reviewed commits |
| `BLOCKED_INCOMPLETE_REVIEW_STATE`         | Snapshot/check/rule pagination or evidence is incomplete, digest mismatches, or late feedback appears                                       | Prior policy writes only                                                   | Completeness blocker, digest/head anchors, and late item IDs when applicable           | Yes                                                                           |
| `OBSERVED_PENDING_OR_FAILED_CI`           | An explicitly requested single readiness read observes a failed, pending, missing, skipped, or unknown required result                      | None                                                                       | Exact current required-check evidence                                                  | No automatic repeat; report and stop                                          |
| `BLOCKED_UNRESOLVED_MATERIAL_FINDING`     | A material finding remains valid, ambiguous, conflicting, or lacks safe disposition                                                         | Prior policy writes; no resolution of affected thread                      | Finding IDs, proof gap, and cycle count                                                | Yes after user direction or new evidence                                      |
| `BLOCKED_UNSAFE_GITHUB_STATE`             | Actor/target/thread identity, head anchor, repository/PR binding, or current target state differs from plan                                 | No attempted mutation after detection                                      | Expected versus current non-secret identity evidence                                   | Yes                                                                           |
| `BLOCKED_SCOPE_REQUIRES_OTHER_REPOSITORY` | A required fix belongs in another repository                                                                                                | Prior policy writes only; no sibling edits                                 | Source finding, affected repository, and dependency                                    | Yes in a separately authorized repository scope                               |
| `BLOCKED_CYCLE_LIMIT_REACHED`             | A material issue remains after two cycles or any third cycle is attempted                                                                   | Writes within the first two cycles only                                    | Remaining findings and all consumed counters                                           | Yes only after a new explicit user decision                                   |
| `BLOCKED_MUTATION_FAILED`                 | One reaction, reply, or resolution call or its required read fails or returns invalid evidence                                              | Earlier successful policy writes plus the single failed attempt            | Operation ID, redacted failure, returned identity if any, and `retry_performed: false` | Yes                                                                           |
| `BLOCKED_UNKNOWN_WRITE_RESULT`            | A mutation response cannot prove whether the requested write applied                                                                        | Earlier successful writes plus the single ambiguous attempt                | Batch/operation/thread identity and all available redacted GitHub evidence             | Yes; inspect manually and never auto-retry                                    |

## Recovery and merge checkpoint

A new normal invocation captures a new stable-feedback state and re-verifies all
anchors. It never appends unreviewed feedback. A recoverable local error stays
within the current invocation; a renewed invocation is required only after a
security blocker, exhausted transient read, or write failure/unknown result.
The terminal report must distinguish what changed, what remains untrusted, and
which user decision is required.

In the explicitly requested readiness path,
`WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION` is a stop state. Only the user
decides whether another review round or a squash merge is requested. The skill
and helper contain no capability to do those things.
