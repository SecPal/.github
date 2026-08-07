<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Finite SecPal PR review workflow

Governance Package 2.2 adds an explicitly invoked skill for processing
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
an open PR, a fully explained commit set, source-appropriate signature evidence
including GitHub verification for user commits when configured, and one
canonical stable-feedback read.

The production registry explicitly supports:

- `SecPal/.github`
- `SecPal/api`
- `SecPal/frontend`
- `SecPal/contracts`
- `SecPal/android`
- `SecPal/GuardGuide`
- `SecPal/guardguide.de`
- `SecPal/secpal.app`
- `SecPal/deployment`

Repository-local `AGENTS.md` and focused instructions remain authoritative.
Commands in the central registry are argument arrays, never shell strings. Bare
executables are limited to the exact direct tools and command forms used by the
production registry; repository-relative, checked-in scripts remain explicit.
Shells, executable-dispatch wrappers, and inline interpreter code therefore
cannot be substituted. Environment-dependent, migration, native-toolchain,
live-service, and deployment validation is represented by explicit manual gates
instead of guessed commands.

## Architecture

The workflow has six narrow parts:

1. [the central skill](../.agents/skills/secpal-pr-review/SKILL.md), which performs
   reasoned technical classification;
2. [the finite contract](../.agents/skills/secpal-pr-review/references/contract.md),
   which defines states, counters, mutation policy, and terminal outcomes;
3. `scripts/secpal_pr_review/fast_path.py`, which defines the stable-feedback,
   volatile-readiness, signed validation-receipt/attestation, and
   batch-resolution contracts;
4. `scripts/secpal-pr-review-actions.py`, the compatible command entry point for
   stable capture, validation attestation, batch resolution, and legacy actions;
5. `scripts/secpal-pr-review.py`, the unchanged Package-2.1 read-only evidence
   verifier used only by explicitly selected forensic/audit snapshot mode; and
6. the workflow-only repository registry, mutation-plan schema, and fast-path
   batch schema under the skill's `references/` directory.

At session start, select the repository entry and materialize only the accepted
Package-2.1 fields into a private session configuration: repository, default
branch, allowed base repositories, reviewer identities, signature policy, check
policy, and capture limits. The workflow-only validation fields never change the
Package-2.1 schema. The action helper reloads the production registry for every
plan validation and rejects unregistered repositories or caller-supplied policy
drift.

Live target reads retain both node and database IDs for reply parents, so an
idempotent reply cannot be attributed to a different comment with only a
coincidentally matching body and writer. The post-merge installer compares the
absolute canonical link text directly and does not depend on GNU-specific
`readlink` options.

## Finite execution

The default forward spine is:

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
    ELSE_VERIFY_UNCHANGED_HEAD
  → RESOLVE_FIXED_THREADS
  → STOP
```

One normal invocation uses zero full snapshots, one stable-feedback read, zero
hosted-CI or Required Check reads, one complete local validation, one holistic
audit, at most one signed remediation commit and ordinary push, and one
target-bound simple resolution pass. Package-2.1/2.2 snapshots remain available
only in explicit forensic mode.

There is no polling, waiting, sleep-and-retry, recursive review loop, automatic
late-feedback incorporation, review request, Ready transition, merge, or
auto-merge.
A correctable local error is repaired in the same invocation, and a read-only
failure may receive one bounded retry. Writes never retry; an unknown write
result stops with its exact operation identity.

## Hosted CI authorization

GitHub-hosted CI is outside ordinary Polyscope and AI execution. A push, PR
creation, review-remediation request, repository convention, previous request,
or thread-resolution request does not authorize reading or summarizing hosted
checks.

Only a current user instruction that explicitly requests CI inspection, check
status, merge readiness, or merge authorization permits one bounded
current-state read. Report that state and stop. Never poll, wait, sleep, repeat
the read automatically, keep the run active for pending checks, or suggest
monitoring. Merge remains separately user-authorized.

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

Compound comments are split into non-empty stable sub-items while retaining
every source ID, and every immutable source must be classified before a policy
write. Duplicates point to one canonical root cause. Outdated items are rechecked
against the current head. Already-fixed claims require test, commit, signature,
and push evidence. Conflicting reviewers are resolved through independent proof,
not authority. Security-weakening suggestions are rejected. Cross-repository
findings block this invocation and never authorize sibling-repository edits.
Every policy operation repeats the exact classification and evidence digest of
its named logical finding.

Green CI is evidence about checks, not proof that feedback is true or that the PR
is ready. Likewise, outdated does not mean invalid and resolved does not mean
fixed. The helper has no keyword classifier; technical truth is established from
repository evidence while deterministic code validates structure and policy transitions.

## Bounded GitHub actions

The reaction/reply/resolution table is normative in the finite contract. In
summary, helpful valid findings may receive 👍, materially misleading invalid
findings may receive 👎, and all other reaction decisions are conservative.
Evidence replies exist only for a non-obvious material misunderstanding. The
workflow never posts fixed/addressed/SHA/progress messages.

The normal path captures stable feedback once, creates one reusable local
validation attestation, pushes one signed commit, and resolves only the named
fixed threads:

```bash
python3 scripts/secpal-pr-review-actions.py resolve-batch \
  --repo SecPal/api \
  --pr 123 \
  --capture-reviewed-state SESSION/reviewed-feedback.json

python3 scripts/secpal-pr-review-actions.py attest-validation \
  --repo SecPal/api \
  --expected-head PARENT_HEAD \
  --reviewed-state SESSION/reviewed-feedback.json \
  --manual-gate-evidence SESSION/manual-gates.json \
  --repo-root /path/to/SecPal/api \
  --output SESSION/validation-receipt.json

# Create the one signed commit with the receipt's `receipt_digest` as its single
# `SecPal-Validation-Receipt` trailer, then bind without rerunning validation.
git commit -S -m "fix: remediate reviewed findings" \
  -m "SecPal-Validation-Receipt: RECEIPT_DIGEST"

python3 scripts/secpal-pr-review-actions.py attest-validation \
  --repo SecPal/api \
  --expected-head HEAD \
  --reviewed-state SESSION/reviewed-feedback.json \
  --repo-root /path/to/SecPal/api \
  --receipt SESSION/validation-receipt.json \
  --bind-commit \
  --output SESSION/validation-attestation.json

python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --expected-head HEAD \
  --reviewed-state SESSION/reviewed-feedback.json \
  --thread-id REVIEW_THREAD_NODE_ID \
  --apply
```

If a registered command fails during the complete validation run, the terminal
JSON diagnostic includes `registered_validation_failure` with the command's
one-based `index`, registry `purpose`, and a safe `category` such as
`non-zero exit`, `timeout`, or `unavailable executable`. The helper still
discards the command's stdout and stderr, leaves only the invalidated receipt
placeholder, and does not run later commands or retry the failed command.

`manual-gates.json` is an ordered JSON array with exactly one
`{"gate": REGISTRY_TEXT, "satisfied": true, "evidence": CONCISE_PROOF}` object
per registered gate. Evidence containing a token prefix, bearer authorization,
or private-key marker is rejected rather than copied into the receipt. The
capture reads one canonical projection containing feedback identities,
digests, states, reactions, actors, the current head, and the reviewed base
branch/SHA. It excludes Required Checks. The complete run produces a staged-tree
receipt that includes the manual-gate evidence. When the tracked tree changed,
the same command binds that receipt after the signed commit only when the
commit's sole parent, tree, signature, and receipt trailer match exactly; this
does not rerun validation. The final attestation binds the repository, finished
head, registry digest, command-set digest, successful result, validated tree,
signed receipt, manual gates, and reviewed-feedback digests. Before the commit
exists on GitHub, binding checks its local signature and configured format only.
When remediation changes no tracked source file and every finding is safely
disposed, verify unchanged local, remote, and PR heads and skip the commit and
push; never create an artificial empty commit.

The simple resolver verifies the exact PR head and target identity without
reading checks, rules, reactions, unrelated feedback, mergeability, or branch
protection. It first reads each target completely and requires its comments to
match the reviewed-state identities and digests. Immediately before each
mutation or successful already-resolved report, it requires two more equal
complete target projections; every mutation response must confirm the exact
resolved thread.

The schema-bound `resolve-batch --apply` path remains available only when the
current user instruction explicitly requests readiness or merge evaluation. In
that path, volatile readiness performs at most one bounded current-state read.
Pending or failed checks are reported as observed facts; they do not start
monitoring, delay fixed-thread resolution, or authorize another automatic read.

Every legacy forensic plan binds the exact repository, PR, immutable digest,
and expected head. Each operation names one source finding, target node/database/
thread identity, expected target state, expected authenticated writer, expected
immutable source actor, classification, evidence digest, payload, and any
returned identity for an already-applied operation. Its compatibility commands
remain:

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

The `validate-plan` example is forensic audit mode. The `react` and `reply`
commands remain compatible for explicitly selected forensic processing.
Individual `resolve` remains available only when the current user instruction
also explicitly requests readiness or merge evaluation; none of these commands
is the normal remediation path. Audit mode performs one bounded current-target
read and zero writes. An individually authorized operation additionally
requires `--apply`. `reply` has the same anchors. `resolve` also requires
`--initial-snapshot` and refuses the write until final evidence proves clean and
matching heads, accepted signatures, complete validation, successful required
checks, no late feedback, and complete dispositions for all unresolved initial
threads and material top-level findings. Each forensic resolution invocation
also runs the checked-in unconditional focused and required local validation
commands and compares the
complete live target-thread comment set with the final snapshot. It then
re-reads applicable required-check rules, branch protection, the current base,
the effective check target, and current required-check outcomes; any drift or
non-successful required result blocks the write. The PR-wide feedback and exact
target reads are repeated after that check gate. Live PR-wide feedback is read
as two complete bounded projections and must match canonically, including all
paginated pages. Applicable rules and check contexts use the same two-projection
stability requirement.

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
Finding sources must exactly equal the initial snapshot's evidence sources.
Final snapshot coverage admits only recorded reaction and reply identities whose
target, payload, parent thread, and authenticated writer exactly match their
operation; those policy writes do not become new findings.
Pending reactions and replies reserve one item from the effective live feedback
capacity before writing, while exact idempotent matches reserve nothing. Inline
reply deltas must also retain the exact parent-comment node ID. A resolution
without a remediation cycle truthfully records `pushed: false`; the helper binds
that value to the session's actual fast-forward-push count.
No-push readiness also requires identical initial and final heads and commit
lists. Remediation readiness requires one new linear commit per recorded signed
push. After the live required-check verification, the helper repeats the
bounded PR-wide feedback and exact target-thread reads before resolving.

## Explicit readiness, forensic snapshots, and recovery

The normal path performs no post-push PR-wide feedback or hosted-CI read. The
simple resolver compares only each named target's exact state before its write.

An explicitly requested readiness path may compare one current stable-feedback
projection and the requested volatile readiness state. It reports that
current-state observation immediately and stops without monitoring.

In explicit forensic mode, the initial snapshot never changes. The one post-cycle-1 capture and one final
capture are comparisons, not extensions. A signed remediation commit may advance
the final head only as a verified descendant that retains every initial commit;
any other head movement or new/edited review feedback ends the invocation and
requires a fresh explicit user request with a new immutable snapshot. An
explicitly requested CI observation reports pending, failed, skipped, missing,
or incomplete required-check evidence once and stops.

After any mutation or evidence blocker, preserve the session report and do not
retry a failed action. No hosted-CI state triggers an automatic or recommended
rerun. The complete terminal-outcome detection table is in the finite contract.

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
touches unrelated user configuration or a sibling repository.

Production rollout is not complete until all of these separately controlled
steps occur:

1. merge the Package-2.2 source PR;
2. install the real user-level skill link;
3. verify discovery from sibling Polyscope workspaces;
4. decide separately how active Ready-transition rulesets that automatically
   request another review should be handled; and
5. run an explicitly authorized disposable-PR end-to-end acceptance.

No real reaction, reply, resolution, reviewer request, or merge belongs in the
source-PR implementation acceptance.
