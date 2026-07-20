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
- valid SSH or OpenPGP signatures for every relevant commit; and
- one complete immutable initial review snapshot.

Do not use this skill for generic code review, creating a PR, requesting any
review, debugging CI without completed feedback, ordinary implementation,
Draft-to-Ready transitions, or merge-only requests. Never request Copilot,
Codex, or human review. Never mark a PR Ready, merge, enable auto-merge, amend a
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

- `scripts/secpal-pr-review.py` for every read-only GitHub snapshot and accepted
  Package-2.1 evidence verification; and
- `scripts/secpal-pr-review-actions.py` only to validate a deterministic plan or
  to apply one individually authorized reaction, evidence reply, or resolution
  after every stated precondition succeeds.

Never import or call the action helper from the evidence helper. Never add a
mutation command to the evidence helper. Execute configured validation commands
as argument arrays in the target repository, without a shell.

## Run the finite invocation

1. Create a mode-`0700` temporary session directory and keep all session output
   there. Initialize the contract counters.
2. Verify repository, topic branch, upstream, clean state, open PR, heads, base,
   exact commits, and signatures. Stop on any discrepancy.
3. Capture exactly one complete immutable initial snapshot with the Package-2.1
   helper. Bind the session to repository, PR, digest, and expected head. Never
   append later feedback to it.
4. Read the authenticated writer through the action helper's exact
   `inspect-actor` query. Split compound comments into stable logical findings
   and classify every item using technical evidence. Do not use keyword
   heuristics or reviewer identity to decide truth.
5. Build and schema-validate a deterministic mutation plan. In audit/default
   mode, do no writes. Apply only an individually authorized operation through
   the action helper with all explicit anchors and `--apply`.
6. For valid actionable findings, reproduce the defect and add a failing test
   first. Make the smallest coherent correction and run focused validation.
7. Run all configured local validation, inspect the complete diff, create one
   signed commit, verify it, recheck the expected remote head, and perform one
   ordinary fast-forward push. Any failure stops the invocation.
8. Perform the one allowed holistic audit across correctness, security, privacy,
   data integrity, lifecycle, rollout, and avoidable complexity.
9. Perform the single post-cycle-1 complete GitHub read. Any new feedback or head
   movement ends this session and requires a fresh explicit user invocation.
10. Use cycle 2 only for an unresolved valid initial-snapshot item or one
    in-scope defect found by the holistic audit. Repeat the same test, signature,
    validation, remote-head, and one-push rules. A third cycle is prohibited.
11. Perform the single final complete GitHub read. Do not retry, poll, sleep, or
    automatically rerun after a push.
12. Resolve an eligible initial-snapshot thread only through one explicitly
    authorized action after the remediation-resolution readiness proof in the
    contract succeeds.
13. Report the terminal outcome and evidence. Stop at
    `WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION`. The user alone decides whether
    another review round is requested and whether the PR may be merged.

Short-circuit immediately to the applicable terminal outcome when a blocker is
detected. Green CI alone never establishes technical truth or merge readiness.

## Mutation plan discipline

Validate plans against
[references/mutation-plan.schema.json](references/mutation-plan.schema.json).
The plan must preserve every source ID, contain no secrets, bind the exact
repository/PR/snapshot/head, and serialize deterministically. It may contain only
`REACTION`, `EVIDENCE_REPLY`, and `THREAD_RESOLUTION` operations.

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
authorized operation identity. Report counter use, head and snapshot anchors,
validation, signatures, CI, unresolved material items, and the exact terminal
outcome. Do not post redundant “fixed,” “addressed,” SHA-status, or progress
comments on the PR.
