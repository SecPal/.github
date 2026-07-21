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
normal_stable_feedback_reads: 2
normal_required_check_reads_before_resolution: 1
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
normal-path prerequisite. The two normal stable-feedback reads are the reviewed
state and one post-push freshness projection. Pagination needed to finish either
bounded logical read does not create a third read.

Security blockers stop immediately. A recoverable local error may be corrected
in the same invocation and reruns only its affected focused command. A
read-only transport or pagination failure may receive one bounded retry. A
mutation failure or unknown write result is never retried.

## Normal fast-path state machine

```text
INITIALIZE
  → READ_STABLE_FEEDBACK_ONCE
  → CLASSIFY_AND_FIX_ALL_CURRENT_FINDINGS
  → FOCUSED_VALIDATION_WHILE_EDITING
  → HOLISTIC_AUDIT
  → COMPLETE_VALIDATION_OF_STAGED_TREE_ONCE
  → SIGNED_COMMIT_AND_BIND_VALIDATION_ATTESTATION
  → NORMAL_PUSH
  → READ_REQUIRED_CHECKS_ONCE
  → READ_STABLE_FEEDBACK_FRESHNESS_ONCE
  → RESOLVE_ELIGIBLE_THREADS_AS_ONE_BATCH
  → WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION
  → TERMINAL
```

A security blocker terminates at the state that detects it. A recoverable local
error does not advance the state or consume a remediation cycle. If
classification proves that no actionable work exists, the invocation reports
`NO_ACTIONABLE_FINDINGS` without creating a remediation commit.

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

`HOLISTIC_AUDIT` runs once and covers correctness, security, privacy, data
integrity, lifecycle, rollout, user control, and avoidable complexity.

`COMPLETE_VALIDATION_OF_STAGED_TREE_ONCE` runs the registered complete command
set once and returns a deterministic receipt binding repository, parent head,
staged-tree SHA, registry digest, command-set digest, successful result, and
reviewed-feedback digests plus explicit satisfied evidence for every registered
manual gate. Time is informational only and cannot determine validity.

`SIGNED_COMMIT_AND_BIND_VALIDATION_ATTESTATION` creates one cryptographically
signed commit with the receipt digest as its single
`SecPal-Validation-Receipt` trailer and proves that its sole parent, tree, and
signed trailer exactly match the receipt. It then returns the final head-bound
attestation without rerunning validation.
`NORMAL_PUSH` proves the remote branch still has the expected predecessor and
makes one ordinary push. Neither state amends, rebases, force-pushes, bypasses
hooks, or uses administrator authority.

`READ_REQUIRED_CHECKS_ONCE` enumerates applicable ruleset and branch-protection
requirements and evaluates volatile Required Checks independently as one bounded
logical read. Missing, pending, failed, skipped, or unknown required results
block. It never polls. `READ_STABLE_FEEDBACK_FRESHNESS_ONCE` compares one current canonical
stable projection with the reviewed feedback. CI-only transitions on the same
head do not affect this comparison. When the expected head is the single
attested remediation descendant, GitHub's derived thread `isOutdated` value may
change from false to true; no other feedback delta is normalized.

`RESOLVE_ELIGIBLE_THREADS_AS_ONE_BATCH` verifies repository, PR, expected/local/
remote heads, clean worktree, attestation, Required Checks, stable feedback, and
all requested thread eligibility once. The batch includes classified findings
whose source-comment identities and body digests match the reviewed projection;
its operations cover every unresolved reviewed thread and name all findings for
their thread. It then performs one bounded last-moment target check and one
write per thread. The target check compares identity, head, open PR/base and
merge state, resolved/outdated thread state, comments, and reactions with the
reviewed projection.
It never reruns complete validation or rereads complete PR feedback between writes.

`WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION` reports evidence and stops. The
workflow never merges. Green CI does not establish technical truth or produce a
ready outcome on its own.

The former three-snapshot state machine remains available only as explicit
forensic/audit compatibility mode. It is not selected automatically and is not
a prerequisite for the normal fast path.

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
technical truth. Green CI does not prove a finding correct or a PR ready.
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

| Classification                             | Reaction                           | Reply                                                                    | Resolution                                       |
| ------------------------------------------ | ---------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------ |
| Valid, relevant, helpful                   | 👍                                 | None                                                                     | After verified correction or proven existing fix |
| Technically false or materially misleading | 👎                                 | Only when invalidity is non-obvious and silence would materially mislead | After evidence is preserved                      |
| Informational                              | None                               | None                                                                     | Only when no material finding remains            |
| Duplicate                                  | None                               | None                                                                     | After canonical finding is safely disposed       |
| Outdated but valid                         | None                               | None                                                                     | After current-head correction proof              |
| Outdated and obsolete                      | None                               | None                                                                     | After current-head obsolescence proof            |
| Ambiguous                                  | None                               | User-facing session report only; no speculative PR reply                 | No                                               |
| Already fixed                              | None                               | No redundant status reply                                                | After proof                                      |
| Superseded                                 | None                               | None                                                                     | After successor is safely disposed               |
| Cross-repository/out of scope              | None                               | Only when a material misunderstanding requires evidence                  | Normally no                                      |
| Security-weakening suggestion              | 👎 only when materially misleading | Evidence reply only when needed                                          | After evidence is retained                       |

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
target. Normal batch resolution instead performs one complete stable-feedback
freshness read before the batch, then one bounded target-feedback consistency
check before each write.

## Stable feedback, readiness, attestation, and batch contract

Stable feedback is one canonical representation containing repository and PR
identity, the bound reviewed head and base branch/SHA, review IDs, top-level comment IDs and body
digests, review-thread and comment IDs and body digests, resolved/outdated state,
reactions, and source actors. Its feedback digest excludes the head solely so a
validation attestation can authorize the expected reviewed-head-to-remediation-
head transition; the state digest includes the head and base. It contains no
Required Check, mergeability, worktree, signature, or validation result.

Volatile readiness separately contains the current PR head, registered default
branch and allowed base repository, base SHA, local and remote heads,
clean-worktree result, Required Checks, mergeability, GitHub merge-state status,
strict-base policy, authenticated actor, signature classifications, signed
validation-receipt trailer, and validation-attestation identity. Required
Checks are read and evaluated once immediately before the freshness comparison
and batch. Stable capture, freshness, checks, and target reads use the same
explicitly selected registry entry; none reloads the default registry.

A validation receipt is produced by the single complete run and binds its staged
tree and normalized satisfied evidence for every registered manual gate. After
the signed commit, that receipt may be bound once only when the commit's parent,
tree, and single `SecPal-Validation-Receipt` trailer match exactly. The final
validation attestation contains at least `repository`, `head_sha`,
`registry_digest`, `command_set_digest`, `successful_result`, validated tree,
receipt digest, and manual-gate evidence. It also binds the reviewed state and
feedback digests. The batch independently reconstructs the receipt from the
live signed commit and rejects a caller-authored attestation file that lacks the
matching signed trailer. Canonical JSON and SHA-256 make it deterministic;
timestamps do not participate. Any bound-value change invalidates the
attestation. It contains no environment dump, command output, credential, or
secret. Manual-gate evidence and every user-controlled batch string are rejected
when they contain the same secret-like patterns prohibited in forensic plans.

A batch input validates against `fast-path-batch.schema.json`. It binds one
repository, PR, expected head, reviewed base branch/SHA, actor, reviewed digests, authorization digest,
classified findings, and a unique ordered set of eligible `THREAD_RESOLUTION`
operations. Each finding binds its thread, exact source-comment identity/body
digest, optional compound-source sub-item identity, classification,
classification-compatible disposition, and evidence digest. Fixed findings
also bind test-evidence and PR-commit digests. Operations name their findings
instead of trusting a free-standing disposition. Every unresolved reviewed
thread and every comment in it has classification coverage before the first
live read. Preflight
and every logical read may retry once only for an unambiguous transient read
failure. Writes never retry. A partial failure records all applied operations,
the exact failed operation, and all later blocked operations, then stops.
An idempotent manual rerun may treat a resolved thread as already applied only
when supplied prior-result evidence has the same authorization digest,
operation/thread identity, and returned mutation identity. If that recorded
resolution is reopened, the rerun blocks instead of resolving it again. Any
external resolution or other stable-feedback delta blocks before the first
write.
An explicit report output is initialized before the first write. If final
persistence fails after a mutation, the helper stops and emits the complete
in-memory applied/failed/blocked evidence to standard error for manual recovery.

User-authored commits are verified locally and must satisfy the configured SSH
or OpenPGP signing policy. GitHub-generated web, squash, and merge commits use GitHub
verification metadata and require `verified = true` with `reason = valid`.
Missing local GitHub GPG key material is `UNKNOWN_LOCAL_KEY`, not an invalid
signature, and does not require key import. Each commit is classified once per
invocation.

## Forensic mutation-plan and action-helper contract

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
- focused and complete required local validation successful;
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

Immediately before each resolution write, the helper runs the repository's
registered focused and required local validation commands without a shell and
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

| Outcome                                   | Exact detection                                                                                                                             | Permitted prior writes                                                     | Required report                                                                         | Fresh invocation?                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `NO_ACTIONABLE_FINDINGS`                  | Every stable reviewed item is classified and none requires correction or user decision; technical evidence is complete                      | Classification-policy writes only                                          | Stable-state/head anchors, all dispositions, counters, CI as evidence rather than truth | No; only if the user later chooses to process new feedback                    |
| `READY_FOR_USER_AUTHORIZED_SQUASH_MERGE`  | All technical, local, signature, push, final-state, CI, and thread-disposition proofs succeed; readiness is not based on CI alone           | Policy writes and eligible resolutions                                     | Full readiness evidence and explicit merge checkpoint                                   | No; wait for the user's separate merge decision                               |
| `NOT_READY_FOR_MERGE`                     | No more specific blocker applies, but complete readiness proof is absent                                                                    | Prior policy writes                                                        | Missing readiness evidence and current anchors                                          | Yes for any renewed processing                                                |
| `BLOCKED_UNCLEAN_WORKTREE`                | Worktree is not clean at entry or a required cleanliness check                                                                              | None when found at entry; otherwise prior policy writes                    | Exact status paths without changing them                                                | Yes after the user restores/accepts state                                     |
| `BLOCKED_HEAD_MOVED`                      | Local, remote, or PR head differs from the expected anchor at any check                                                                     | None before feedback capture; otherwise prior policy writes                | Expected and observed OIDs and detection state                                          | Yes                                                                           |
| `BLOCKED_UNEXPLAINED_COMMIT`              | Exact PR commit set contains a commit not explained by the reviewed session                                                                 | None                                                                       | Commit OIDs and why provenance is unexplained                                           | Yes after user decision                                                       |
| `BLOCKED_INVALID_SIGNATURE`               | A user commit lacks a locally valid configured SSH/OpenPGP signature, or a GitHub-generated commit lacks valid GitHub verification metadata | No correction/push/resolution; prior policy writes possible if found later | Commit source and selected verification evidence                                        | Yes after new signed history is user-authorized; never amend reviewed commits |
| `BLOCKED_INCOMPLETE_REVIEW_STATE`         | Snapshot/check/rule pagination or evidence is incomplete, digest mismatches, or late feedback appears                                       | Prior policy writes only                                                   | Completeness blocker, digest/head anchors, and late item IDs when applicable            | Yes                                                                           |
| `BLOCKED_FAILED_OR_PENDING_CI`            | Any required check is failed, pending, missing, skipped contrary to policy, or unknown                                                      | Prior policy writes; no resolution                                         | Exact required-check evidence                                                           | Yes; no polling in this invocation                                            |
| `BLOCKED_UNRESOLVED_MATERIAL_FINDING`     | A material finding remains valid, ambiguous, conflicting, or lacks safe disposition                                                         | Prior policy writes; no resolution of affected thread                      | Finding IDs, proof gap, and cycle count                                                 | Yes after user direction or new evidence                                      |
| `BLOCKED_UNSAFE_GITHUB_STATE`             | Actor/target/thread identity, head anchor, repository/PR binding, or current target state differs from plan                                 | No attempted mutation after detection                                      | Expected versus current non-secret identity evidence                                    | Yes                                                                           |
| `BLOCKED_SCOPE_REQUIRES_OTHER_REPOSITORY` | A required fix belongs in another repository                                                                                                | Prior policy writes only; no sibling edits                                 | Source finding, affected repository, and dependency                                     | Yes in a separately authorized repository scope                               |
| `BLOCKED_CYCLE_LIMIT_REACHED`             | A material issue remains after two cycles or any third cycle is attempted                                                                   | Writes within the first two cycles only                                    | Remaining findings and all consumed counters                                            | Yes only after a new explicit user decision                                   |
| `BLOCKED_MUTATION_FAILED`                 | One reaction, reply, or resolution call or its required read fails or returns invalid evidence                                              | Earlier successful policy writes plus the single failed attempt            | Operation ID, redacted failure, returned identity if any, and `retry_performed: false`  | Yes                                                                           |
| `BLOCKED_UNKNOWN_WRITE_RESULT`            | A mutation response cannot prove whether the requested write applied                                                                        | Earlier successful writes plus the single ambiguous attempt                | Batch/operation/thread identity and all available redacted GitHub evidence              | Yes; inspect manually and never auto-retry                                    |

## Recovery and merge checkpoint

A new normal invocation captures a new stable-feedback state and re-verifies all
anchors. It never appends unreviewed feedback. A recoverable local error stays
within the current invocation; a renewed invocation is required only after a
security blocker, exhausted transient read, or write failure/unknown result.
The terminal report must distinguish what changed, what remains untrusted, and
which user decision is required.

At `WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION`, stop. Only the user decides
whether another review round or a squash merge is requested. The skill and
helper contain no capability to do those things.
