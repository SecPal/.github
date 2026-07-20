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
maximum_remediation_cycles: 2
maximum_logical_github_state_captures: 3
maximum_holistic_audits: 1
maximum_signed_remediation_commits: 2
maximum_fast_forward_pushes: 2
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
A third remediation cycle is prohibited.
Every failed API call, local validation, signature check, push, reaction, reply,
or resolution ends the invocation with evidence.

The three logical captures are the immutable initial snapshot, one post-cycle-1
state read, and one final state read. Pagination within one complete capture is
not another logical capture. A skipped remediation cycle does not authorize an
extra capture, commit, audit, or push.

## Exact forward state machine

```text
INITIALIZE
  → VERIFY_LOCAL_AND_PR_STATE
  → CAPTURE_ONE_IMMUTABLE_SNAPSHOT
  → CLASSIFY_ALL_SNAPSHOT_ITEMS
  → APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES
  → REMEDIATION_CYCLE_1
  → LOCAL_VALIDATE_SIGN_COMMIT_FAST_FORWARD_PUSH
  → HOLISTIC_AUDIT
  → POST_CYCLE_1_SINGLE_GITHUB_READ
  → OPTIONAL_REMEDIATION_CYCLE_2
  → LOCAL_VALIDATE_SIGN_COMMIT_FAST_FORWARD_PUSH
  → FINAL_SINGLE_GITHUB_READ
  → RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE
  → WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION
  → TERMINAL
```

A blocker terminates at the state that detects it; it never jumps forward. If
classification proves that no actionable work exists, the invocation reports
`NO_ACTIONABLE_FINDINGS` without creating a remediation commit. If cycle 2 is
not justified, its validation/commit/push state is a no-op and does not consume
those counters.

### State rules

`INITIALIZE` requires explicit invocation, loads the registry, creates one
mode-`0700` temporary session directory, initializes counters, and performs no
GitHub write.

`VERIFY_LOCAL_AND_PR_STATE` proves the repository, current topic branch,
upstream, clean worktree, open PR, local/remote/PR heads, base, exact commit set,
signatures, and absence of unexplained commits.

`CAPTURE_ONE_IMMUTABLE_SNAPSHOT` uses the accepted read-only Package-2.1 helper
to capture metadata, all reviews and top-level comments, all threads and replies,
resolved/outdated state, reactions, commits and signatures, applicable rules,
and required checks. The repository, PR, digest, and expected head bind the
session. No later feedback is appended.

`CLASSIFY_ALL_SNAPSHOT_ITEMS` splits compound feedback and independently proves
each classification from source, tests, and repository context.

`APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES` permits only schema-valid,
individually authorized operations that match the policy table below.

`REMEDIATION_CYCLE_1` reproduces each valid finding, adds a failing test first,
implements the smallest coherent fix, and runs focused validation.

`LOCAL_VALIDATE_SIGN_COMMIT_FAST_FORWARD_PUSH` runs complete configured local
validation, reviews the full diff, creates one cryptographically signed commit,
verifies the commit, proves the remote branch still equals the expected old
head, and makes one ordinary fast-forward push. It never amends, force-pushes,
uses `--no-verify`, rewrites reviewed history, bypasses protection, or uses
`--admin`.

`HOLISTIC_AUDIT` runs once and covers correctness, security, privacy, data
integrity, lifecycle, rollout, and avoidable complexity.

`POST_CYCLE_1_SINGLE_GITHUB_READ` is one complete fresh capture. It detects head
movement, new feedback, checks, and unresolved review state. Late feedback requires a fresh explicit user invocation and never silently enters this
session.

`OPTIONAL_REMEDIATION_CYCLE_2` is allowed only for a still-valid initial-snapshot
finding or one in-scope defect found by the holistic audit. The same test,
validation, signing, remote-head, and push rules apply.

`FINAL_SINGLE_GITHUB_READ` is the third and final logical capture. There are no
retries or polling.

`RESOLVE_ELIGIBLE_THREADS_FROM_VERIFIED_STATE` resolves only an eligible
initial-snapshot thread after the complete resolution proof below.

`WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION` reports evidence and stops. The
workflow never merges. Green CI does not establish technical truth or produce a
ready outcome on its own.

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

Split compound comments into stable sub-items while preserving every source
review, thread, and comment ID. A duplicate names one canonical root cause.
Recheck outdated feedback against the current head. An already-fixed finding
requires test evidence plus a validly signed, pushed commit on the snapshot head.
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

Before a reaction, read existing reactions, refuse a duplicate, and never remove
another actor's reaction. Before a reply, search existing replies and refuse a
duplicate evidence reply. Never post “fixed,” “addressed,” commit-SHA status, or
progress messages. Before resolution, re-read the thread and refuse a resolved
or changed target.

## Mutation-plan and action-helper contract

The schema-bound plan contains its version, repository, PR, immutable snapshot
digest, expected head, creation state, cycle, finite session counters, stable
logical findings, and operations. Every operation contains an ID, one of
`REACTION`, `EVIDENCE_REPLY`, or `THREAD_RESOLUTION`, exact target node/database
and parent-thread IDs, expected current target state, expected authenticated
writer identity, expected immutable source actor identity, classification,
evidence digest, operation payload, returned mutation identity when already
applied, and any resolution preconditions.

Plans are deterministic, secret-free, and bound to the exact repository, PR,
snapshot digest, and expected head SHA. A changed head invalidates a plan.
Prohibited kinds are review request, Ready transition, label, issue, review
submission, merge, auto-merge, comment deletion, review dismissal, and branch
write.

The action helper has only the read-only `inspect-actor`, `validate-plan`,
`react`, `reply`, and `resolve` commands. Every mutation command requires the
plan, operation ID, exact repository, PR, digest,
head, and explicit `--apply`. Without `--apply`, it performs no mutation. There
is no generic API passthrough. The helper uses argument arrays, an exact endpoint
and GraphQL-document allowlist, a pinned host, no shell, no Git write, no retry,
no polling, and no sleep. It reads target state first, verifies actor, target,
head, and idempotency, applies at most once, and reports the returned identity.
Later-state plans retain identities for earlier authorized writes; every other
new or changed comment, review, thread state, reply, or reaction is late feedback.

## Remediation-resolution readiness

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
- no new feedback after the immutable snapshot;
- no head movement or unsafe GitHub state; and
- no counter limit exceeded.

Resolution remains read-only until one individual operation is explicitly
applied. Already-resolved or changed targets are refused idempotently.

## Terminal outcomes

“Prior policy writes” below means only individually authorized reactions or
exception evidence replies performed before the blocker; no write is allowed
after detection.

| Outcome                                   | Exact detection                                                                                                                   | Permitted prior writes                                                     | Required report                                                                        | Fresh invocation?                                                             |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `NO_ACTIONABLE_FINDINGS`                  | Every immutable-snapshot item is classified and none requires correction or user decision; technical evidence is complete         | Classification-policy writes only                                          | Snapshot/head anchors, all dispositions, counters, CI as evidence rather than truth    | No; only if the user later chooses to process new feedback                    |
| `READY_FOR_USER_AUTHORIZED_SQUASH_MERGE`  | All technical, local, signature, push, final-state, CI, and thread-disposition proofs succeed; readiness is not based on CI alone | Policy writes and eligible resolutions                                     | Full readiness evidence and explicit merge checkpoint                                  | No; wait for the user's separate merge decision                               |
| `NOT_READY_FOR_MERGE`                     | No more specific blocker applies, but complete readiness proof is absent                                                          | Prior policy writes                                                        | Missing readiness evidence and current anchors                                         | Yes for any renewed processing                                                |
| `BLOCKED_UNCLEAN_WORKTREE`                | Worktree is not clean at entry or a required cleanliness check                                                                    | None when found at entry; otherwise prior policy writes                    | Exact status paths without changing them                                               | Yes after the user restores/accepts state                                     |
| `BLOCKED_HEAD_MOVED`                      | Local, remote, or PR head differs from the expected anchor at any check                                                           | None before snapshot; otherwise prior policy writes                        | Expected and observed OIDs and detection state                                         | Yes                                                                           |
| `BLOCKED_UNEXPLAINED_COMMIT`              | Exact PR commit set contains a commit not explained by the reviewed session                                                       | None                                                                       | Commit OIDs and why provenance is unexplained                                          | Yes after user decision                                                       |
| `BLOCKED_INVALID_SIGNATURE`               | Any relevant commit lacks a locally and GitHub-valid accepted SSH/OpenPGP signature                                               | No correction/push/resolution; prior policy writes possible if found later | Commit and signature evidence                                                          | Yes after new signed history is user-authorized; never amend reviewed commits |
| `BLOCKED_INCOMPLETE_REVIEW_STATE`         | Snapshot/check/rule pagination or evidence is incomplete, digest mismatches, or late feedback appears                             | Prior policy writes only                                                   | Completeness blocker, digest/head anchors, and late item IDs when applicable           | Yes                                                                           |
| `BLOCKED_FAILED_OR_PENDING_CI`            | Any required check is failed, pending, missing, skipped contrary to policy, or unknown                                            | Prior policy writes; no resolution                                         | Exact required-check evidence                                                          | Yes; no polling in this invocation                                            |
| `BLOCKED_UNRESOLVED_MATERIAL_FINDING`     | A material finding remains valid, ambiguous, conflicting, or lacks safe disposition                                               | Prior policy writes; no resolution of affected thread                      | Finding IDs, proof gap, and cycle count                                                | Yes after user direction or new evidence                                      |
| `BLOCKED_UNSAFE_GITHUB_STATE`             | Actor/target/thread identity, head anchor, repository/PR binding, or current target state differs from plan                       | No attempted mutation after detection                                      | Expected versus current non-secret identity evidence                                   | Yes                                                                           |
| `BLOCKED_SCOPE_REQUIRES_OTHER_REPOSITORY` | A required fix belongs in another repository                                                                                      | Prior policy writes only; no sibling edits                                 | Source finding, affected repository, and dependency                                    | Yes in a separately authorized repository scope                               |
| `BLOCKED_CYCLE_LIMIT_REACHED`             | A material issue remains after two cycles or any third cycle is attempted                                                         | Writes within the first two cycles only                                    | Remaining findings and all consumed counters                                           | Yes only after a new explicit user decision                                   |
| `BLOCKED_MUTATION_FAILED`                 | One reaction, reply, or resolution call or its required read fails or returns invalid evidence                                    | Earlier successful policy writes plus the single failed attempt            | Operation ID, redacted failure, returned identity if any, and `retry_performed: false` | Yes                                                                           |

## Recovery and merge checkpoint

Every fresh invocation captures a new immutable snapshot and re-verifies all
anchors; it never resumes by appending state. The terminal report must distinguish
what changed, what remains untrusted, and which user decision is required.

At `WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION`, stop. Only the user decides
whether Copilot Review, Codex Review, another review round, or a squash merge is
requested. The skill and helper contain no capability to do those things.
