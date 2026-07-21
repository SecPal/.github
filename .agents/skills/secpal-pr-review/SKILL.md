---
name: secpal-pr-review
description: Process completed review feedback for one named SecPal repository and pull request, only after an explicit PR-feedback remediation request. Do not use for generic review, PR creation, review requests, CI-only debugging, ordinary implementation, or merge-only work.
---

# SecPal PR Review

Use this skill only when the user explicitly asks to process already-completed
pull-request feedback for a specific repository and PR number. This skill is not a reviewer: it independently verifies reviewer leads and remediates only findings
that source, tests, and repository context prove valid.

## Required inputs and boundaries

Require all of the following before starting:

- an explicit PR-feedback remediation request;
- the exact `owner/repository` and pull request number;
- a clean worktree on the current topic branch with its upstream configured;
- matching local, remote, and PR head OIDs;
- an open pull request, an understood base, and an exact explained commit set;
- locally verified SSH or OpenPGP signatures for user-authored commits, as
  permitted by the repository registry;
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

- `scripts/secpal-pr-review-actions.py resolve-batch` for the normal stable
  feedback capture and guarded batch-resolution path;
- `scripts/secpal-pr-review-actions.py attest-validation` for one deterministic
  complete-validation attestation bound to the finished local head; and
- `scripts/secpal-pr-review.py` plus the legacy action commands only when the
  user explicitly selects forensic/audit snapshot mode.

Never import or call the action helper from the evidence helper. Never add a
mutation command to the evidence helper. Execute configured validation commands
as argument arrays in the target repository, without a shell.

## Run the finite invocation

1. Create a mode-`0700` temporary session directory. Capture stable feedback
   once with `resolve-batch --capture-reviewed-state`; do not create a Package
   2.1 or Package 2.2 snapshot in normal mode.
2. Split compound comments into stable logical findings and classify every item
   from source, tests, and repository context. Bind each finding's typed source
   identity/digest, optional unresolved thread, classification, disposition,
   and evidence digest in the batch. Cover top-level reviews, conversation
   comments and their reactions, stable pull-request reactions, and unresolved-
   thread comments and their reactions. PR-level `EYES` activity markers are
   volatile workflow state rather than review feedback. Never infer truth from
   reviewer identity, keywords, or CI.
3. Reproduce every valid finding, add a failing test first, make the smallest
   coherent corrections, and use focused validation while editing.
4. Perform the one holistic audit across correctness, security, privacy, data
   integrity, lifecycle, rollout, and avoidable complexity. Fix material
   in-scope defects before the complete validation.
5. Stage the finished tree and run complete registered local validation exactly
   once through `attest-validation`, supplying explicit satisfied evidence for
   every registered manual gate. Preserve its deterministic staged-tree,
   parent-head, registry, command-set, manual-gate, result, and reviewed-feedback
   receipt.
6. Create one signed commit containing exactly that staged tree, use
   the receipt digest as its single `SecPal-Validation-Receipt` trailer, and use
   `attest-validation --bind-commit` to verify that signed binding without
   rerunning validation. Recheck the remote head and push once.
7. Read applicable rules and Required Checks once as one bounded logical read.
   Pending, failed, missing, or unknown required results block; never poll.
8. Perform one lightweight stable-feedback freshness read. A same-head CI
   transition is irrelevant to this comparison. The single attested remediation
   head may cause GitHub's derived `isOutdated` state to change from false to
   true; every other unexpected head, comment, reaction, or thread-state change
   blocks before the first write.
9. Resolve all eligible threads through one schema-bound `resolve-batch
--apply`. Verify readiness, attestation, checks, and stable feedback once;
   between writes retain one bounded target check that verifies identity, head,
   open PR/base state, thread state, comments, and reactions without rereading
   complete PR feedback.
10. Report the terminal outcome and evidence. Stop at
    `WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION`. The user alone decides whether
    another review round is requested and whether the PR may be merged.

Short-circuit immediately to the applicable terminal outcome when a blocker is
detected. Green CI alone never establishes technical truth or merge readiness.

## Fast-path and forensic-plan discipline

Validate fast-path batch inputs against
`references/fast-path-batch.schema.json`. One batch may contain only
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

The stable-feedback projection contains review identities, body digests,
thread/comment identities and state, stable reactions, actors, repository, PR,
head, and the reviewed base branch/SHA. It excludes PR-level `EYES` activity
markers and contains no Required Check results.
Volatile readiness separately contains heads, the registered default/base
repository boundary, Required Checks, mergeability and merge-state policy,
worktree, signatures, the signed validation-receipt trailer, and the
validation-attestation identity. Capture, freshness, checks, and target reads
must use the one explicitly selected registry entry.

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
authorized operation identity. Report counter use, stable-state or forensic
snapshot anchors,
validation attestation, signature-source classifications, CI, stable-feedback
freshness, batch results, unresolved material items, and the exact terminal
outcome. Do not post redundant “fixed,” “addressed,” SHA-status, or progress
comments on the PR.
