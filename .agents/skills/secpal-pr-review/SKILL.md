---
name: secpal-pr-review
description: Process completed review feedback for one named SecPal repository and pull request after an explicit remediation request, or handle explicitly named fixed-thread resolution-only requests after the findings were validated, committed, and pushed. Do not use for generic review, PR creation, review requests, CI-only debugging, ordinary implementation, or merge-only work.
---

# SecPal PR Review

Use this skill only when the user explicitly asks to process already-completed
pull-request feedback for a specific repository and PR number, or asks to
resolve explicitly named threads whose findings have already been handled as
defined below. This skill is not a reviewer: it independently verifies reviewer
leads and remediates only findings that source, tests, and repository context
prove valid.

## Simple fixed-thread resolution

When the user asks only to resolve explicitly named review threads whose
findings have already been evaluated, fixed where necessary, validated,
committed, and pushed, use the central source repository's
`scripts/secpal-resolve-fixed-threads.py`. Require the exact repository, pull
request number, expected current head OID, reviewed-state file, and thread IDs.
Also require the captured reviewed-state digest and successful validation
evidence in the final attestation for a new verified fix commit. A raw
validation receipt for an unchanged head is not authenticated by that existing
commit and cannot authorize resolution. Require the target repository root and
an eligibility manifest that covers every requested thread exactly with an
allowed classification/disposition, finding IDs, evidence digest, and the fix
commit. The command rejects a swapped state file, a non-matching local commit,
and stale, missing, incomplete, unauthenticated, or differently bound evidence
before any GitHub read.
The command first reads every target completely and requires its current
comment identities, body digests, and resolution state to match that reviewed
state. It then performs two complete stable target rechecks of the open PR,
expected head, membership, resolved/outdated state, and canonical
target-comment state immediately before each write or successful
already-resolved report.

Invoke the resolver in write mode; omitting `--apply` is only a dry run:

```bash
python3 scripts/secpal-resolve-fixed-threads.py \
  --repo OWNER/REPOSITORY \
  --pr PULL_REQUEST_NUMBER \
  --repo-root /path/to/OWNER/REPOSITORY \
  --expected-head FULL_40_CHARACTER_HEAD_OID \
  --reviewed-state REVIEWED_STATE.json \
  --expected-reviewed-state-digest REVIEWED_STATE_SHA256 \
  --validation-evidence VALIDATION_EVIDENCE.json \
  --eligibility-evidence ELIGIBILITY_EVIDENCE.json \
  --thread-id REVIEW_THREAD_NODE_ID \
  --apply
```

Repeat `--thread-id REVIEW_THREAD_NODE_ID` for each additional fixed thread.

This resolution-only path does not capture or reclassify PR-wide feedback, run
validation, inspect CI or readiness, create commits, push, or make a merge
decision. Report the exact resolved and already-resolved targets, then stop.
Use the full workflow below only when the user asks to process feedback,
perform remediation, audit readiness, or evaluate merge authorization.

## Required inputs and boundaries

For the full feedback-remediation workflow, require all of the following before
starting:

- an explicit PR-feedback remediation request;
- the exact `owner/repository` and pull request number;
- a clean worktree on the current topic branch with its upstream configured;
- matching local, remote, and PR head OIDs;
- an open pull request, an understood base, and an exact explained commit set;
- locally verified SSH or OpenPGP signatures for user-authored commits, as
  permitted by the repository registry, plus valid GitHub verification metadata
  when the registry requires it;
- GitHub `verified: true`, `reason: valid` metadata for GitHub-generated
  commits; and
- one canonical stable-feedback read containing no Required Check results.

Do not use this skill for generic code review, creating a PR, requesting any
review, debugging CI without completed feedback, ordinary implementation,
Draft-to-Ready transitions, or merge-only requests. Never request another
review. Never mark a PR Ready, merge, enable auto-merge, amend a
reviewed commit, force-push, bypass hooks, or use administrator privileges.

Read [references/contract.md](references/contract.md) completely before acting.
Load the matching entry from
[references/repositories.json](references/repositories.json), validated against
[references/repositories.schema.json](references/repositories.schema.json).
Repository-local `AGENTS.md` and focused instruction files remain authoritative
for development rules.

## Locate the trust surfaces

Resolve this skill directory canonically. Its central source repository is three
directories above it. Use that source repository's:

- `scripts/secpal-pr-review-actions.py resolve-batch` for normal stable-feedback
  capture only; its guarded readiness batch is available only when the current
  user instruction explicitly requests readiness or merge evaluation;
- `scripts/secpal-pr-review-actions.py attest-validation` for one deterministic
  complete-validation attestation bound to the finished local head; and
- `scripts/secpal-resolve-fixed-threads.py` for default post-push resolution of
  eligible fixed threads and for the resolution-only path defined above; and
- `scripts/secpal-pr-review.py` plus evidence-only legacy action commands only
  when the user explicitly selects forensic/audit snapshot mode. Any legacy
  command that reads hosted-CI readiness additionally requires the current user
  instruction to explicitly request readiness or merge evaluation.

Never import or call the action helper from the evidence helper. Never add a
mutation command to the evidence helper. Execute configured validation commands
as argument arrays in the target repository, without a shell.

## Run the finite invocation

The following state machine applies only to the full feedback-remediation path.

1. Create a mode-`0700` temporary session directory. Capture stable feedback
   once with `resolve-batch --capture-reviewed-state`; do not create a Package
   2.1 or Package 2.2 snapshot in normal mode.
2. Split compound comments into stable logical findings and classify every item
   from source, tests, and repository context. Preserve each finding's source
   identity/digest, optional unresolved thread, classification, disposition,
   and evidence. Cover top-level reviews, conversation comments, and unresolved
   thread comments. Reactions and unrelated feedback are not thread-resolution
   preconditions. Never infer truth from reviewer identity, keywords, or CI.
3. Reproduce every valid finding, add a failing test first, make the smallest
   coherent corrections, and use focused validation while editing.
   Never use a complete, repository-wide, or aggregate suite as focused
   validation by default. If the relevant regression is available only through
   such a suite, isolate the smallest direct test, filter, or fixture before
   running it. A registered focused-only command explicitly authorized by its
   matching manual gate is the bounded exception. It remains excluded from
   unconditional complete validation.
4. Perform the one holistic audit across correctness, security, privacy, data
   integrity, lifecycle, rollout, and avoidable complexity. Complete all source,
   provenance, edge-case, and diff inspection here, and fix material in-scope
   defects before the complete validation.
5. Stage the finished tree and run the registered unconditional focused commands
   plus every required local validation exactly once through
   `attest-validation`, supplying explicit satisfied evidence for every
   registered manual gate. Preserve its deterministic staged-tree,
   parent-head, registry, command-set, manual-gate, result, and reviewed-feedback
   receipt. Do not continue discovery or change the tree after this step begins.
   A failed command produces no receipt and is a terminal security blocker for
   this invocation. Do not change the tree or retry any complete command.
   Require a new explicit remediation invocation so any correction receives
   focused validation and a fresh holistic audit before its single complete
   validation. Never repeat a successful complete validation.
6. When remediation changed the staged tree, create one signed commit containing
   exactly that tree, use the receipt digest as its single
   `SecPal-Validation-Receipt` trailer, and use `attest-validation --bind-commit`
   to verify that signed binding and its local signature without rerunning
   validation. When remediation changes no tracked source file and every finding
   is safely disposed, prove the local, remote, and PR heads still equal the
   reviewed head and skip the commit and push states; never create an artificial
   empty commit. A receipt created after that existing commit is not
   authenticated by it and cannot authorize a thread-resolution mutation; stop
   without resolution when no authenticated fix-commit attestation exists.
7. For the changed-tree path only, recheck the remote predecessor, push once
   without bypassing local hooks, and verify that local, remote, and PR heads
   equal the signed commit. Do not inspect hosted CI as a consequence of the
   push.
8. Resolve every eligible fixed thread with
   `scripts/secpal-resolve-fixed-threads.py --apply`, binding the exact
   repository, PR, repository root, current head OID, reviewed-state file and
   digest, successful validation evidence for that fix commit, exact
   per-thread eligibility evidence, and thread IDs. This
   reads only the named targets, requires their comments to equal the reviewed
   feedback, and does not reclassify or gate on unrelated PR state.
9. Report the commit, branch, remote synchronization, local validation,
   worktree state, PR identity, and resolution results, then stop. Merge remains
   separately authorized by the current user instruction.

Short-circuit immediately to the applicable terminal outcome when a blocker is
detected. Green CI alone never establishes technical truth or merge readiness.

## Fast-path and forensic-plan discipline

Only when the current user instruction explicitly requests readiness or merge
evaluation, validate fast-path batch inputs against
`references/fast-path-batch.schema.json`. Such a batch may contain only
`THREAD_RESOLUTION` operations and must bind repository, PR, expected head,
reviewed base branch/SHA, authenticated actor, reviewed-state and feedback digests, and eligible
classified findings. The reviewed state must originate from an open PR. Every
top-level review/comment and its reactions, stable pull-request reaction, unresolved
reviewed thread, and comment/reaction in it must be covered; PR-level `EYES`
activity markers are excluded before digesting. Each resolution names exactly its threaded
findings, and classification/disposition pairs must follow policy. A
partial failure stops later writes, reports every applied/failed/blocked target,
and never retries a write. Applied-target report entries are audit output, not
reusable authorization. A manual rerun with an already-resolved or otherwise changed thread fails closed.

The normal stable-feedback projection contains review identities, body digests,
thread/comment identities and state, stable reactions, actors, repository, PR,
head, and the reviewed base branch/SHA. It excludes PR-level `EYES` activity
markers and contains no Required Check results.
Explicitly requested volatile readiness separately contains heads, the registered default/base
repository boundary, Required Checks, mergeability and merge-state policy,
worktree, signatures, the signed validation-receipt trailer, and the
validation-attestation identity. A readiness request performs one bounded
current-state read, reports it, and stops without polling, waiting, sleeping, or
automatic repetition. Merge remains separately user-authorized.

The following immutable mutation-plan rules remain available only for explicit
forensic/audit mode.

Validate plans against
[references/mutation-plan.schema.json](references/mutation-plan.schema.json).
The plan must preserve every source ID, contain no secrets, match the selected
production registry entry, bind each operation to the same immutable
repository/PR/snapshot/finding/target/head state, and serialize deterministically.
It may contain only `REACTION`, `EVIDENCE_REPLY`, and `THREAD_RESOLUTION`
operations.

`inspect-actor` is an exact read-only identity query used to bind the intended
writer. Each operation separately binds its immutable source actor. Without
`--apply`, an action command may make one bounded idempotency read but
must make zero writes. With `--apply`, it reads the current target, confirms the
expected actor, target, and head, applies at most once, and reports the returned
mutation identity. Record that identity in later-state plans so authorized
writes can be distinguished from late feedback. A failure ends the invocation
without retry.

## Reporting

Report every finding's sources, classification, proof, disposition, and any
authorized operation identity. For ordinary remediation, report only the
commit, branch, remote synchronization, local validation, worktree state, PR
identity, and resolution results. Report hosted-CI state only when the current
user instruction explicitly requests one status or readiness read; report the
observed state once and stop without suggesting monitoring or another run. Do
not post redundant “fixed,” “addressed,” SHA-status, or progress comments on the
PR.
