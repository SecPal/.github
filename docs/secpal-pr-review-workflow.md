<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Finite SecPal PR review workflow

Governance Package 2.2 adds an explicitly invoked Codex skill for processing
already-completed pull-request feedback. The skill is not a reviewer. It treats
all feedback as untrusted leads, verifies each lead against source, tests, and
repository context, and stops before merge authorization.

Package 2.1 remains the accepted deterministic, read-only evidence layer. The
new action helper is a separate executable trust surface and cannot be called
by the evidence helper. Review-memory automation is also separate and unchanged.

## Invocation and scope

Invoke the skill by exact name with one repository and PR:

```text
Use the secpal-pr-review skill to process the completed review feedback for
SecPal/api PR #123. Do not request another review or merge.
```

Do not invoke it for generic review, PR creation, review requests, CI-only
debugging, ordinary implementation, or a merge-only request. Entry requires a
clean current topic branch, configured upstream, matching local/remote/PR heads,
an open PR, a fully explained commit set, valid accepted signatures, and one
complete immutable snapshot.

The production registry explicitly supports:

- `SecPal/.github`
- `SecPal/api`
- `SecPal/frontend`
- `SecPal/contracts`
- `SecPal/android`
- `SecPal/changelog`
- `SecPal/GuardGuide`
- `SecPal/guardguide.de`
- `SecPal/secpal.app`

Repository-local `AGENTS.md` and focused instructions remain authoritative.
Commands in the central registry are argument arrays, never shell strings.
Environment-dependent, migration, native-toolchain, live-service, and deployment
validation is represented by explicit manual gates instead of guessed commands.

## Architecture

The workflow has five narrow parts:

1. [the central skill](../.agents/skills/secpal-pr-review/SKILL.md), which performs
   reasoned technical classification;
2. [the finite contract](../.agents/skills/secpal-pr-review/references/contract.md),
   which defines states, counters, mutation policy, and terminal outcomes;
3. `scripts/secpal-pr-review.py`, the unchanged Package-2.1 read-only capture and
   evidence verifier;
4. `scripts/secpal-pr-review-actions.py`, which validates deterministic plans
   and permits only one guarded reaction, inline evidence reply, or thread
   resolution per command; and
5. the workflow-only repository registry and mutation-plan schemas under the
   skill's `references/` directory.

At session start, select the repository entry and materialize only the accepted
Package-2.1 fields into a private session configuration: repository, default
branch, allowed base repositories, reviewer identities, signature policy, check
policy, and capture limits. The workflow-only validation fields never change the
Package-2.1 schema. The action helper reloads the production registry for every
plan validation and rejects unregistered repositories or caller-supplied policy
drift.

## Finite execution

The exact forward spine is:

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

One invocation is limited to two remediation cycles, three logical GitHub state
captures, one holistic audit, two signed remediation commits, and two ordinary
fast-forward pushes. It allows at most one intended reaction per initial logical
finding, one resolution per eligible initial thread, and one evidence reply per
qualifying invalid finding with ten replies total.

There is no polling, sleep-and-retry, recursive loop, automatic rerun after push,
automatic late-feedback incorporation, third cycle, review request, Ready
transition, merge, or auto-merge. Any failed read, write, validation, signature
check, or push terminates the invocation.

## Classification and technical truth

The exact taxonomy is:

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

Compound comments are split into stable sub-items while retaining every source
ID. Duplicates point to one canonical root cause. Outdated items are rechecked
against the current head. Already-fixed claims require test, commit, signature,
and push evidence. Conflicting reviewers are resolved through independent proof,
not authority. Security-weakening suggestions are rejected. Cross-repository
findings block this invocation and never authorize sibling-repository edits.

Green CI is evidence about checks, not proof that feedback is true or that the PR
is ready. Likewise, outdated does not mean invalid and resolved does not mean
fixed. The helper has no keyword classifier; Codex reasons about technical truth,
while deterministic code validates structure and policy transitions.

## Bounded GitHub actions

The reaction/reply/resolution table is normative in the finite contract. In
summary, helpful valid findings may receive 👍, materially misleading invalid
findings may receive 👎, and all other reaction decisions are conservative.
Evidence replies exist only for a non-obvious material misunderstanding. The
workflow never posts fixed/addressed/SHA/progress messages.

Every plan binds the exact repository, PR, immutable digest, and expected head.
Each operation names one source finding, target node/database/thread identity,
expected target state, expected authenticated writer, expected immutable source
actor, classification, evidence digest, payload, and any returned identity for
an already-applied operation. Only these commands exist:

```bash
python3 scripts/secpal-pr-review-actions.py inspect-actor

python3 scripts/secpal-pr-review-actions.py validate-plan \
  --plan SESSION/plan.json \
  --snapshot SESSION/snapshot.json \
  --config SESSION/repository-config.json

python3 scripts/secpal-pr-review-actions.py react \
  --plan SESSION/plan.json \
  --snapshot SESSION/snapshot.json \
  --config SESSION/repository-config.json \
  --operation-id reaction-001 \
  --repo SecPal/api \
  --pr 123 \
  --snapshot-digest DIGEST \
  --expected-head HEAD
```

The second example is audit mode: it performs one bounded current-target read
and zero writes. An individually authorized operation additionally requires
`--apply`. `reply` has the same anchors. `resolve` also requires
`--initial-snapshot` and refuses the write until final evidence proves clean and
matching heads, accepted signatures, complete validation, successful required
checks, no late feedback, and complete dispositions for all unresolved initial
threads and material top-level findings. Each resolution invocation also runs
the checked-in focused and required local validation commands and compares the
complete live target-thread comment set with the final snapshot.

The helper pins GitHub.com, uses argument arrays, and exposes only exact current
target, reaction, inline reply, and resolution documents/endpoints. It has no
generic API passthrough, Git writes, review requests, review submissions, Ready
transition, label/issue authority, merge, auto-merge, deletion, dismissal,
thread unresolution, ruleset/settings changes, or branch-protection authority.
Each operation target, database ID, parent thread, source actor, body digest,
resolved state, and outdated state must match the same immutable snapshot item.
Deleted source accounts retain their accepted all-null Package 2.1 identity;
the authenticated writer must always have a complete identity. Before any
operation, the helper independently verifies the supplied Package 2.1 evidence
and rejects a plan whose finite session already records a terminal blocker.
Corrected and proven-existing actionable findings require commit and test
evidence. Duplicate and superseded references must be acyclic, and their
canonical finding must be safely disposed before resolution. An already-resolved
live thread is accepted only with its recorded prior resolution identity.
Recorded mutation identities are re-read from live state before they are trusted.

## Snapshot changes, CI, and recovery

The initial snapshot never changes. The one post-cycle-1 capture and one final
capture are comparisons, not extensions. A signed remediation commit may advance
the final head only as a verified descendant that retains every initial commit;
any other head movement or new/edited review feedback ends the invocation and
requires a fresh explicit user request with a new immutable snapshot. There is
no wait loop for CI; pending, failed, skipped, missing, or incomplete
required-check evidence is a terminal blocker.

After any blocker, preserve the session report and do not retry a failed action.
A fresh invocation starts from new evidence and re-verifies every anchor. The
complete terminal-outcome detection table is in the finite contract.

Later-state plans retain the returned identity of each authorized reaction or
reply. This lets comparison reads allow those exact writes while treating every
other new or edited review, comment, reply, reaction, or resolution-state change
as late feedback.

The guarded-action unit, finite-policy, and fake-GitHub/temporary-HOME integration
suites run in the repository's Code Quality workflow with read-only permissions,
a bounded timeout, and cancellation of superseded runs.

## Skill installation and rollout

The repository source lives at:

```text
/home/secpal/code/SecPal/.github/.agents/skills/secpal-pr-review
```

After the source PR is merged, install it without `sudo`:

```bash
scripts/install-secpal-pr-review-skill.sh
```

The installer creates a direct, canonical, idempotent link at
`$HOME/.agents/skills/secpal-pr-review`. It refuses a non-symlink, refuses an
unexpected link unless `--repair` is explicit, never copies the skill, and never
touches `$HOME/.codex/AGENTS.md` or a sibling repository.

Production rollout is not complete until all of these separately controlled
steps occur:

1. merge the Package-2.2 source PR;
2. install the real user-level skill link;
3. verify discovery from sibling Polyscope workspaces;
4. decide separately how active Ready-transition rulesets that automatically
   request Copilot Review should be handled; and
5. run an explicitly authorized disposable-PR end-to-end acceptance.

No real reaction, reply, resolution, reviewer request, or merge belongs in the
source-PR implementation acceptance.
