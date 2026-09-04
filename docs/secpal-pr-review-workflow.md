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

The workflow has eight narrow parts:

1. [the central skill](../.agents/skills/secpal-pr-review/SKILL.md), which performs
   reasoned technical classification;
2. [the finite contract](../.agents/skills/secpal-pr-review/references/contract.md),
   which defines states, counters, mutation policy, and terminal outcomes;
3. `scripts/secpal_pr_review/fast_path.py`, which defines the stable-feedback,
   volatile-readiness, signed validation-receipt/attestation, and
   batch-resolution contracts;
4. `scripts/secpal-pr-review-actions.py`, the compatible command entry point for
   stable capture, validation attestation, batch resolution, and legacy actions;
5. `scripts/secpal-create-late-classification.py`,
   `scripts/secpal-create-late-disposition.py`, and
   `scripts/secpal_pr_review/late_disposition.py`, which create and verify the
   narrowly scoped detached post-final-push disposition artifact;
6. `scripts/secpal-pr-review.py`, the unchanged Package-2.1 read-only evidence
   verifier used only by explicitly selected forensic/audit snapshot mode; and
7. the workflow-only repository registry, current mutation-plan schema, exact
   legacy mutation-plan v1.0 schema, and fast-path batch schema under the
   skill's `references/` directory; and
8. `scripts/secpal_pr_review/lifecycle_authority.py`, the separately adoptable
   persistent lifecycle-authority primitive and independent verifier.

The action helper validates persisted mutation plans against their original
versioned shape. Version 1.0 retains legacy findings without `follow_up` and
cannot authorize `TRACKED_AS_FOLLOW_UP`; version 1.1 is required for tracked
follow-up identity. Mixed and unknown versions fail closed.

## Persistent lifecycle authority

Lifecycle-authority schema 1.0 is an append-only chain rooted in exactly one
authenticated delivery initialization and its canonical `INITIALIZED_DRAFT`
event. The initialization binds the ordinary validation receipt and final
attestation to the repository, issue, initial PR, and exact initial head. Its
maintained anchor digest derives both the persistent lifecycle identity and
canonical genesis event identity. Each non-genesis snapshot binds the
exact predecessor authority digest and head, one independently signed typed
event, the persistent repository/issue/lifecycle/PR identity, and the derived
next state. The closed state records finite review and remediation counters,
explicit Cycle-3 absence, Draft/Ready state and transition history, and bounded
exceptional recovery and continuation history. Head advancement and authorized
PR rebinding preserve every lifecycle fact.

The installed repository registry is the lifecycle trust-policy source. It
separately assigns transition and authority signer roles, accepted signature
formats, SSH public keys, OpenPGP fingerprints, and unique initialization
anchors, with at most one initialization root per delivery issue. For every
enrolled issue the policy also selects the exact current terminal authority
digest, current PR, and current head. The public verifier does not accept
consumer signer sets, verification callbacks, or current-tip selectors: it
loads this maintained policy and invokes concrete `ssh-keygen` or GnuPG
detached-signature verification. Signer assertions inside evidence are never
sufficient.

The public verifier accepts only a canonical serialized evidence bundle. It
rejects duplicate and unknown fields, non-finite JSON, noncanonical encodings,
and caller-preparsed mappings before recomputing every state from genesis. Git
object identities are exactly 40-hex SHA-1 or 64-hex SHA-256 values. A verified
binding exposes the authority and initialization digests, persistent lifecycle
identity, exact head, and normalized history digests for later consumers.
The empty anchor list is the intentional fail-closed pre-adoption state. Once
enrolled, same-head transitions advance the maintained terminal digest, stale
prefixes fail, and replacement PRs retain the original root through
`PR_REBOUND` rather than creating another genesis.

This primitive does not observe GitHub, mutate Ready/Draft state, process review
events, replace pull requests, or orchestrate recovery. Existing ordinary
one-parent delivery evidence remains valid and no consumer is automatically
migrated. Adoption by #745 and full lifecycle orchestration under #692 are
separate work.

The complete registered validation graph explicitly runs the lifecycle-
authority unit suite; its security regressions are not left to a manual focused
invocation.

## Lifecycle enrollment and current publication

The publication boundary distinguishes native and legacy adoption. A
`NATIVE_LIFECYCLE` has a maintained #750 root and complete authenticated history
from inception. A genuinely older delivery may use one explicitly authorized,
dedicated-role-signed `LEGACY_ADOPTION_CHECKPOINT`. The checkpoint openly makes
the migration authority the trust root for the imported finite baseline; it
does not relabel unavailable old evidence as cryptographically reconstructed.
Every post-checkpoint change is an ordinary #750 successor, and another legacy
checkpoint or baseline reset is forbidden.

One separately versioned `EXACT_STATE_ADOPTION` enrollment semantic covers an
explicitly authorized, previously unenrolled delivery whose independently
observed platform chronology cannot truthfully be represented as an ordinary
derived event prefix. Its signed proof binds the exact repository, issue, PR,
head, tree, signature status, receipt, adoption-time source attestation,
normalized observations, complete finite state, supporting evidence, and actual
adoption time. A separately signed authorization binds that complete evidence
and intended state with exactly one bounded use. The proof is the cryptographic
genesis and CURRENT baseline; the observed timestamps remain observations and
`ordinary_lifecycle_events` remains empty. It neither reorders platform history
nor backdates authority.

Proof assembly accepts only the verifier-derived external-evidence boundary.
The maintained validation receipt and final-attestation verifier derives the
source-evidence identity; canonical commit-signature and observation admission
derives the remaining facts. Callers cannot nominate trusted evidence digests.
Observation-derived Ready and exceptional history entries bind their canonical
observation digest and never carry an ordinary event-authorization digest.

Exact-state adoption reuses the maintained migration signer role, enrollment
uniqueness, protected publication journal, CAS, lifecycle identity and authority
digest conventions. Later transitions use the ordinary successor verifier, and
Ready integration consumes the same published prior-authority manifest/tag
boundary with the adopted tree, receipt, and adoption-time attestation bound by
the proof. Native deliveries cannot self-select adoption, a second enrollment
root remains forbidden, and adoption is not a lifecycle state, Recovery,
Continuation, or permission to cure ordinary ordering after the fact.

For a later head-changing ordinary successor, the immutable adoption proof
remains the genesis while the signed successor authority binds verifier-derived
current-head tree, receipt, final attestation, and source-evidence identity.
Prior-Ready verification authenticates those current facts and the unchanged
genesis chain; it never treats genesis evidence as evidence for a later head.

The maintained migration role uses public credential material distinct from
ordinary, lifecycle-transition, and publication signers; policy loading rejects
credential overlap even when the duplicate key is assigned another principal.
Legacy enrollment ends exactly at the checkpoint terminal, so post-checkpoint
continuations and PR rebinding cannot be folded into the migration root.

The maintained registry contains only trust policy: publication, native-genesis
admission, and migration signer roles; the exact GitHub endpoint, publication
branch, and live ruleset identity and required protections; static initialization
roots; exact historical native compatibility-publication identities; and the
one closed issue 736 bootstrap-repair identity.
New candidate heads, terminal digests, and current publication objects are not
registered there. Dynamic events form one signed
linear journal on `refs/heads/secpal-lifecycle-publications` outside delivery
trees. The live ruleset prohibits deletion and non-fast-forward updates without
bypass; lease-based CAS separately rejects stale cooperative writers.

The verifier authenticates that protection, observes the branch tip once, and
checks immutable ancestry. The newest valid event for each lifecycle is
CURRENT. Consumer expectations are post-verification constraints; callers
cannot supply the remote, branch, trust, migration checkpoint, or terminal
selector. Publication Git operations use a controlled bare repository and
closed environment, preventing ambient URL rewrites and transport overrides.
For native adoption, a separately signed genesis admission must be reachable in
journal ancestry before the first lifecycle publication. A branch-local static
anchor cannot substitute for admission. The separately maintained pre-#774
compatibility registry binds repository, issue, PR, initial head,
initialization digest, historical proof mode, exact enrollment publication OID,
and exact signed publication digest. Only those immutable historical enrollment
objects bypass admission ordering; a later candidate carrying the same
initialization cannot. Later journal successors use a private
publication-only verification path for the same initialization root and full
signed transition chain; authenticated journal ancestry then selects CURRENT.
The ordinary #750 verifier keeps its static current-tip requirement, and no
consumer-controlled bypass is exposed.

The one `BOOTSTRAP_REPAIR_NATIVE_GENESIS` operation for issue 736 binds the
maintained exact original initialization, receipt, attestation, signer,
signature, and enrollment publication. It is allowed to follow that existing
enrollment, appends without rewriting history, and selects no terminal. See
[Native Lifecycle Genesis Admission](native-lifecycle-genesis-admission.md).

Publication does not derive lifecycle state, orchestrate lifecycle events, or
implement two-parent integration. Those remain owned by #750, #692, and #745
respectively. Repositories with no enrolled publication remain valid, while a
consumer explicitly requesting published authority fails closed.

## Finite lifecycle orchestration

`scripts/secpal_pr_review/lifecycle_orchestration.py` authenticates #752 CURRENT
publication and consumes #750 state before deciding any replacement, recovery,
Ready/Draft, review, CI, integration-observation, additional-review, or late-
feedback event. The decision contains the unchanged persistent lifecycle ID,
finite counters, explicit Cycle-3 absence, Ready history, and exceptional-event
counts. It selects at most one typed lifecycle transition and performs no
mutation itself.

Replacement uses `PR_REBOUND` and cannot create another lifecycle root.
An already-authorized normal remediation commit advances the head with
`REMEDIATION_COMPLETED` while preserving Ready and requiring fresh evidence.
Exceptional recovery is available only on an exhausted Ready lifecycle with an
exact new head, exact finding IDs, and one separately reasoned bounded user
authorization. It preserves `Draft=false`, requires fresh head-bound evidence,
and never selects another Ready transition. `Ready -> Draft` and any later
`Draft -> Ready` each require their own exact user authorization and preserve
the same lifecycle and consumed counters. User-controlled orchestration accepts
only canonical signed authorization evidence bound to the exact CURRENT
publication, lifecycle authority, PR, head, operation, reason, and scope;
caller-constructed request fields are not authority.

GitHub review submissions, review comments/threads, CI observations, reopen
events, and validated Ready integrations are bounded evidence observations, not
lifecycle events. They select no review request, counter change, recovery,
Ready/Draft transition, or recursive processing. One explicitly authorized
additional review permits one bounded current-head assessment and stops.
Its signed authorization is consumed through an append-only
`ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED` transition before assessment. That
transition preserves Ready and all review/remediation counters while making the
same authorization stale after publication.

Late feedback consumes #673's canonical classification, including independent
`technically_blocking` and `mechanically_blocking` facts. A high-risk or material
technical blocker stops merge readiness and requires an explicit recovery
decision; it cannot become Cycle 3 or a non-blocking follow-up. A canonical
`NON_BLOCKING_FOLLOWUP` additionally requires #689's exact live open and
structurally complete follow-up verification. Successful guarded resolution is
reported as `SAFELY_DISPOSITIONED_TRACKED`, never fixed, implemented, or
completed. #724 remains the separate authenticated unchanged-head path for the
late dispositions in its exact allowlist.

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

`OUTSIDE_PR_SCOPE + OUT_OF_SCOPE` remains non-resolution-eligible. A material
finding may instead use `TRACKED_AS_FOLLOW_UP` only when review judgment proves
the current PR does not implement it and binds one exact canonical GitHub issue
identity (`repository`, positive `issue_number`, and matching canonical
`issue_url`) into the authenticated eligibility evidence. Immediately before
resolving that exact source thread, the resolver uses the canonical work-graph
reader to prove the same follow-up remains accessible, open, and structurally
complete. The follow-up may be blocked and need not be ready or started.
Resolution means safely tracked outside this PR, not fixed or completed.
The legacy mutation and readiness-batch schemas preserve the same identity but
cannot resolve this disposition because they do not consume the signed
eligibility manifest. The authenticated simple resolver is the only mutation
path for `TRACKED_AS_FOLLOW_UP`.

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
fixed threads. Finalize `SESSION/thread-eligibility.json` from the completed
classifications and dispositions before starting the complete validation:

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
  --eligibility-evidence SESSION/thread-eligibility.json \
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
  --eligibility-evidence SESSION/thread-eligibility.json \
  --bind-commit \
  --output SESSION/validation-attestation.json

python3 scripts/secpal-resolve-fixed-threads.py \
  --repo SecPal/api \
  --pr 123 \
  --repo-root /path/to/SecPal/api \
  --expected-head HEAD \
  --reviewed-state SESSION/reviewed-feedback.json \
  --expected-reviewed-state-digest REVIEWED_STATE_SHA256 \
  --validation-evidence SESSION/validation-attestation.json \
  --eligibility-evidence SESSION/thread-eligibility.json \
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
receipt that includes the manual-gate evidence and the canonical digest of the
pre-validation eligibility manifest. When the tracked tree changed,
the same command binds that receipt after the signed commit only when the
commit's sole parent, tree, signature, and receipt trailer match exactly; this
does not rerun validation. The final attestation binds the repository, finished
head, registry digest, command-set digest, successful result, validated tree,
signed receipt, manual gates, authenticated eligibility digest, and
reviewed-feedback digests. Before the commit exists on GitHub, binding checks
its local signature and configured format only.
When remediation changes no tracked source file and every finding is safely
disposed, verify unchanged local, remote, and PR heads and skip the commit and
push; never create an artificial empty commit. Because a receipt produced after
that existing commit is not authenticated by it, the raw receipt cannot
authorize thread resolution. Stop without resolution unless a final attestation
is bound to a new signed fix commit. The sole exception is an exact
post-final-push, technically non-blocking thread authorized through the
separately signed late-disposition path documented below; that path reuses the
already verified final delivery attestation and does not create a new receipt.

### Explicit Ready-head integration evidence

Ordinary remediation and recovery continue to require one parent. A separately
user-authorized mechanical integration into an already-Ready delivery PR uses
`attest-validation --integration-evidence` and the closed version-1.1
`TWO_PARENT_READY_INTEGRATION` topology. The invocation also supplies the exact
delivery issue, authorization ID, and expected signer. Its evidence fixes parent
1 to the previously authenticated Ready head and parent 2 to the explicitly
authenticated current registered `main` snapshot, in that order, and requires
exactly two parents.

The prior Ready state is supplied as a separate closed
`READY_INTEGRATION_PRIOR_AUTHORITY` manifest. Its digest is authenticated by a
signed annotated tag on the prior delivery head, and the binder independently
verifies that head's ordinary receipt, final attestation, tree, signature, and
accepted signer. It also verifies the maintained #750/#752 protected-journal
CURRENT publication and binds its lifecycle authority digest, proof mode,
publication identity, and exact exceptional recovery and continuation history.
Ordinary typed integration is the canonical `HEAD_ADVANCED`
transition: it preserves the exact authenticated exceptional-recovery and
exceptional-continuation history and consumes neither budget. A later
`EXCEPTIONAL_RECOVERY` or `EXCEPTIONAL_CONTINUATION` remains a distinct,
explicitly authorized lifecycle action. The manifest's claimed receipt must
equal the prior commit trailer, ordinary receipt reconstructed with the registry
committed at that prior head, and final-attestation receipt. The mutable tag
ref is resolved once; target, signature, signer, trailer, and diagnostics all
use the resulting immutable annotated-tag OID. OpenPGP signing-subkey output is
accepted only when its authenticated primary fingerprint is the configured
authority. The manifest binds the lifecycle identity and unchanged
review/remediation counters, so inline integration booleans cannot establish
Ready or lifecycle authority. Receipt creation performs one trusted GitHub
observation of the open Ready PR and the repository's live default-branch tip;
the live PR head must equal parent 1 and that live tip must equal both the
explicitly authorized SHA and parent 2. The creation-time PR base OID is not a
current-tip selector. The read is not caller-provided evidence and any
missing, malformed, or drifted result fails closed without retry.

Before the candidate is bound, the same complete registered validation produces
a fresh receipt for the combined staged tree. The signed integration candidate
carries one `SecPal-Validation-Receipt` trailer and one
`SecPal-Integration-Evidence` trailer. Binding reconstructs the receipt, verifies
the ordered parents, combined tree, both trailers, configured signature policy,
expected signer identity, stable-feedback and validation-execution digests,
explicit eligibility, and the exact raw delta between the authenticated
mechanical merge tree and the validated tree. Every permitted manual conflict-
resolution path, mode, status, old object, and new object must appear exactly in
that canonical delta; unlisted file drift fails closed. Exit-zero merge-tree
output must have no conflict paths or manual delta. Exit-one output must name a
canonical non-empty conflict set; every path must be changed or deleted, no
other path may change, and retained text conflict markers are rejected. The
synthetic conflict tree itself is never accepted as a resolved candidate.

When the integration must authorize exact reviewed-thread resolution,
`--eligibility-evidence` may accompany `--integration-evidence`. The receipt
binds both digests and binding emits the distinct version-1.2
`ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION`. The guarded
resolver accepts that kind only with the canonical integration artifact and
only after the integration-specific verifier authenticates the ordered parents,
tree, both trailers, reviewed state, expected signer, and eligibility. The
historical version-1.1 integration attestation remains valid for integration
authentication but cannot authorize resolution. Other evidence-mode
combinations remain closed.

The integration evidence proves unchanged unrestricted-review, remediation,
exceptional-recovery, and exceptional-continuation counters, no Cycle 3, no
review request, no Ready transition, and preserved `Draft=false` / `Ready=true`.
After the signed integration head is created, its fresh lifecycle authority is
derived from the authenticated predecessor through `HEAD_ADVANCED` and
published through the canonical lifecycle-publication boundary. It is not
remediation and cannot be replayed through
the remediation path. Conversely, ordinary remediation evidence cannot select
the integration path. The helper does not create the integration commit, push a
branch, observe post-push checks, transition the PR, or authorize merging. After
push, fresh head-bound checks, stable feedback, eligibility, and readiness must
be assessed in a separately authorized evidence phase; platform-triggered
reviews are evidence only.

An exceptional recovery after `BLOCKED_CYCLE_LIMIT_REACHED` is available only
when a new, explicit user instruction selects
`attest-validation --exceptional-recovery-evidence`. The closed
`READY_EXCEPTIONAL_RECOVERY` artifact and eligibility manifest bind the exact
reviewed findings/threads, prior Ready head/tree, recovery tree, issue/PR,
stable feedback, `review=1/1`, `remediation=2/2`, `Cycle 3=false`, preserved
Ready state, and exceptional-recovery count one. The ordinary single-parent
receipt and final attestation carry its digest. This path cannot reset the
finite lifecycle, manufacture Cycle 3, transition Ready state, or authorize a
recursive recovery.

The simple resolver first verifies the caller-captured reviewed-state digest,
successful validation attestation, actual local signed commit, and exact
per-thread eligibility manifest authenticated by the signed validation
receipt. A Recovery-bound ordinary attestation additionally retains and passes
`--delivery-issue`, `--exceptional-recovery-evidence`, and
`--exceptional-recovery-authorization` from the accepted Recovery authority.
The shared verifier alone may authenticate the installed ruleset for
`refs/heads/secpal-lifecycle-publications`. The resolver then verifies the exact
PR head and target identity without reading checks, delivery-PR rules,
reactions, unrelated feedback, mergeability, or merge readiness. It
reads each target completely and requires its comments to match the
reviewed-state identities and digests. The complete original ordered eligibility
remains authoritative after a partial result: an exact target captured
unresolved but now resolved is an authenticated zero-write satisfaction, while
an exact unresolved target follows the ordinary guarded mutation path and all
other drift fails closed. Immediately before a tracked-follow-up
mutation it also performs the authenticated, fail-closed live work-graph
verification described above. Immediately before each mutation or successful
already-resolved report, it requires two more equal
complete target projections; every mutation response must confirm the exact
resolved thread.

Detached late disposition has one narrower alternative final boundary for the
exact `SecPal/.github` #810 / PR #821 delivery. Accepted-main policy may prove
that its authenticated zero-thread final reviewed state and final
receipt/attestation omitted eligibility authentication. The complete detached
late-authority tuple selects late mode. In that mode only, omitting the final
eligibility path yields a typed authenticated absence; it does not yield or
recreate an eligibility manifest. A supplied path selects manifest verification;
present, null, malformed, or stale eligibility evidence fails and never selects
absence mode. Final eligibility evidence outside late mode is rejected.

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

An explicitly requested post-final-push resolution-only action first creates
one canonical detached-signed `late-classification.schema.json` artifact for
exactly one named thread, then creates one canonical
`late-disposition.schema.json` artifact for that same thread.
Creation first verifies the unchanged final delivery head, tree,
receipt trailer, attestation, canonical final eligibility artifact, origin, and
accepted commit signature. It proves the named thread absent from both the
complete authenticated final reviewed state and eligibility set, verifies that
every eligible thread belongs to the reviewed state, derives the actual
delivery signer fingerprint, reads that named thread twice, and signs the
classification with that same OS-account identity. The disposition creator
verifies the classification signature and exact live binding and computes its
digest internally. SSH and OpenPGP are supported.
The resolver independently repeats the final-delivery verification, verifies
both canonical artifacts and detached signatures against the derived signer,
and compares exact live head, thread, top-level comment node/database identity,
body digest, reply state, resolved/outdated state, classification, disposition,
technical-blocking flag, and guarded action before resolving. This path is only
`INVALID_FALSE_OR_MISLEADING + DISPROVEN_WITH_EVIDENCE` with
`technically_blocking=false`; it consumes no review/remediation counter and has
no commit, push, Ready, CI, issue, label, review, or merge capability.
The same origin predicate is independently re-established by disposition
creation and resolution. “Post-final-push” names this lifecycle boundary; it
does not claim cryptographic proof of GitHub wall-clock push ordering.

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
