<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Finite SecPal PR review workflow

Governance Package 2.2 adds an explicitly invoked skill for processing
already-completed pull-request feedback. The skill is not a reviewer. It treats
all feedback as untrusted leads, verifies each lead against source, tests, and
repository context. The feedback helper itself has no merge capability; a
larger delivery may continue through separately maintained lifecycle and merge
boundaries when the current user instruction already authorizes them.

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

## Proof validity and preflight

`SIMPLIFY_BEFORE_EXTEND` applies to the workflow itself:

```text
PROMPT_BOUNDARY != EVIDENCE_INVALIDATOR
MECHANICAL_CHECKPOINT != USER_DECISION_BOUNDARY
```

A new prompt or internal phase alone invalidates no authenticated proof. Use
the smallest explicit invalidation model already implied by each proof:

- PR/head-bound proof is invalidated by a relevant head change.
- Staged-tree and validation proof is invalidated by a relevant tree change.
- Lifecycle CURRENT proof is invalidated by a new CURRENT publication.
- Stable-feedback proof is invalidated by relevant feedback or reviewed-head change.
- Work-graph proof validity is owned by `docs/work-graph-contract.md`; refresh
  its canonical read after a relevant native graph mutation.
- Volatile readiness and merge evidence is freshly read at its mutation boundary.

No freshness database, cache, signer, evidence schema, or daemon represents
these rules. The first entry into one delivery performs the relevant full
preflight. Later work in that delivery uses same-delivery delta preflight:
refresh only facts whose invalidators may have occurred, plus the fresh
operation-specific state required immediately before a critical mutation. A
commit, tool handoff, prompt continuation, or internal phase is not by itself a
reason to reread the complete graph, ADR, issue, PR, and CI state.

Before every lifecycle mutation, derive the operation and its exact
preconditions from authenticated current maintained repository authority.
Prompt text may bind identity, intent, scope, mutation budget, expected result,
acceptance, and stop conditions. Those expectations are assertions to verify,
not a second
lifecycle contract. If those expectations conflict with the maintained
contract, fail closed before mutation and report the discrepancy.

Inside one explicitly authorized delivery, commit, push, receipt and
attestation binding, lifecycle publication, eligible thread resolution, and
bounded read-back are mechanical checkpoints. Draft PR creation, an eligible
Ready transition, bounded provider observation, finding classification,
in-contract remediation, and an eligible conditionally authorized merge are
likewise mechanical when the maintained gate selects them. Reaching one does
not require another prompt. New authority is required for material scope
expansion, another independently deliverable responsibility, Exceptional
Recovery, an unresolved material design choice, or an operation not explicitly
or conditionally authorized by the current instruction.

A current instruction may grant conditional current user authorization for a
later bounded mutation, for example: evaluate the final maintained merge gate
and, if and only if it passes for the unchanged authenticated authorized head,
perform the canonical squash merge; otherwise stop without merge. This retains
explicit current authority and does not let an earlier instruction, prompt
expectation, transport, or successful check authorize a mutation.

Native Polyscope PR creation is preferred when available. Its absence is a tool
transport fact, not a user decision: an already-authorized delivery may use the
smallest maintained GitHub fallback, preserve repository/base/branch/title/body
identity, report the actual creation path and association, and continue. The
fallback gains no lifecycle authority merely by existing.

```text
POLYSCOPE_NATIVE_PR_UNAVAILABLE != USER_DECISION_BOUNDARY
```

## Review-provider terminality

For the one bounded external review phase, normalize each relevant configured
and triggered provider to the existing observable facts `NOT_APPLICABLE`,
`NOT_TRIGGERED`, `QUEUED`, `PENDING`, `RUNNING`, `COMPLETED_NO_FINDINGS`,
`COMPLETED_WITH_FINDINGS`, `FAILED`, or `INDETERMINATE`. This normalization is
ephemeral workflow judgment, not a persistent state machine.

`QUEUED`, `PENDING`, `RUNNING`, `FAILED`, and `INDETERMINATE` are not successful
terminal review. A provider need not be a branch-protection Required Check to
block the maintained merge gate. In particular:

```text
NO_REVIEW_FINDINGS_YET != REVIEW_COMPLETE
ZERO_THREADS_WHILE_REVIEW_RUNNING != STABLE_FEEDBACK
CI_GREEN + MERGEABLE + REVIEW_RUNNING = MERGE_FORBIDDEN
```

Capture stable feedback only when
`ALL_TRIGGERED_REVIEW_PROVIDERS_TERMINAL = YES`, after the last provider reaches
`COMPLETED_NO_FINDINGS` or `COMPLETED_WITH_FINDINGS`. Absence of comments never
proves completion. Capture one complete bounded snapshot for that reviewed head,
then classify the complete set before remediation. Do not remediate one provider
at a time while another is running. Relevant later feedback or a reviewed-head
change invalidates that snapshot.

The existing bounded capture query enforces the visible provider gate before
admitting stable feedback. It rejects non-terminal, malformed, forged,
duplicated, or wrong-head Codex summaries, requires a Codex summary for a Ready
PR, and rejects a pending Copilot review request. The query discards provider
status after the gate, preserving the existing stable-feedback schema and
digest. Provider absence remains `NOT_TRIGGERED` only where the maintained
observable boundary has no affirmative trigger evidence.

When the current instruction authorizes full delivery and the environment can
wait, observe only maintained review-provider status at bounded intervals of
approximately 60 to 90 seconds for approximately 30 minutes total. This passive
observation does not consume another unrestricted review, request a review, or
poll unrelated hosted CI. Continue automatically once every triggered provider
has successful terminal evidence. If the full window expires, report
`REVIEW_NOT_TERMINAL` with the authenticated head and exact non-terminal
providers, perform no merge, and do not claim that user approval is needed. The
same workspace may resume when external state changes. No unbounded polling and
No Cycle 3 are permitted.

The unrestricted external review budget remains one. Remediation never creates
a second unrestricted external review cycle. Changed remediation requires a
fresh final-candidate self-review that asks both whether the findings are fixed
and what new defect, bypass, authority leak, regression, inconsistency, or
avoidable complexity the correction introduced. Material security or authority remediation
requires first-principles design reassessment: compare the final design with the
reviewed design, look for shared flawed abstractions and a smaller replacement,
and adversarially test the resulting trust boundary. Small ordinary remediation
does not acquire that heavyweight ceremony.

Immediately before merge, freshly authenticate the exact PR and head, base,
OPEN/Ready state, mergeability, Required Checks, lifecycle CURRENT, final
validation receipt/attestation, review submissions, provider terminality,
stable-feedback validity, unresolved threads, finding dispositions, and current
merge authority. Apply these hard failures without inference from green CI:

```text
ANY_TRIGGERED_REVIEW_PROVIDER_NON_TERMINAL -> MERGE_FORBIDDEN
FINAL_STABLE_FEEDBACK_CAPTURED_BEFORE_PROVIDER_TERMINALITY -> MERGE_FORBIDDEN
ANY_UNCLASSIFIED_MATERIAL_FINDING -> MERGE_FORBIDDEN
ANY_VALID_ACTIONABLE_BLOCKING_FINDING_UNREMEDIATED -> MERGE_FORBIDDEN
ANY_UNRESOLVED_BLOCKING_THREAD -> MERGE_FORBIDDEN
VALIDATION_OR_LIFECYCLE_OR_CI_OR_MERGEABILITY_GATE_FAILS -> MERGE_FORBIDDEN
```

Only the canonical merge selected by that complete fresh gate may consume the
current conditional authority. Never force merge or bypass protection. After
merge, freshly verify that the PR merged, its delivery issue completed as
expected, accepted `main` contains the intended validated semantics, relevant
invariants still pass on accepted main, and no downstream issue was mutated
unintentionally. Do not report `MERGED_COMPLETE` before that read-back succeeds.

The bounded normal path preserves these explicit self-review conclusions:

```text
MERGE_WHILE_REVIEW_RUNNING = IMPOSSIBLE
UNBOUNDED_REVIEW_LOOP = NO
SECOND_UNRESTRICTED_REVIEW = NO
NEW_LIFECYCLE_STATE = NO
NEW_COUNTER = NO
NEW_TRUST_ROOT = NO
POLYSCOPE_NATIVE_PR_REQUIRED_FOR_DELIVERY = NO
MANUAL_PR_CREATION_REQUIRED = NO
NORMAL_LEAF_CAN_REACH_MERGED_COMPLETE = YES
```

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

Initialization schema 1.1 additionally accepts exactly one maintained
`AUTHENTICATED_PRE_ENROLLMENT_DRAFT_INTEGRATION_HEAD` proof. That proof is
returned only after the separately typed
`PRE_ENROLLMENT_DRAFT_INTEGRATION` verifier authenticates the signed candidate,
its two ordered Draft/current-main parents, exact tree, receipt, final
attestation, signer, PR, issue, repository, and bounded conflict evidence. A
generic merge commit cannot supply this proof. The resulting lifecycle still
starts with the ordinary `INITIALIZED_DRAFT` state and zero review,
remediation, Ready-transition, exceptional-recovery, and
exceptional-continuation counters; Cycle 3 remains absent. Native genesis is
then admitted and enrolled through the admission-first publication boundary.
The integration itself is not a lifecycle transition.

## Pre-enrollment Draft current-main integration

An open Draft delivery that has not entered lifecycle authority may use the
closed `PRE_ENROLLMENT_DRAFT_INTEGRATION` topology. Its first parent is the
authenticated live Draft PR head and its second parent is the freshly observed
registered default-branch head. The canonical work graph must identify the
delivery as a READY leaf, and the protected lifecycle journal must prove both
CURRENT and native-genesis absence. A signed authorization fixes the exact
repository, issue, PR, both parents, expected signer, and operation identity.

The shared Git mechanics derive the mechanical merge tree, canonical conflict
paths, raw resolution delta, ordered parents, and candidate signature. Clean
merges require exact mechanical-tree equality. Conflict-bearing merges require
one exact changed/deleted entry per conflict path, no other path, and no
retained conflict markers. Complete validation binds the frozen tree in
`PRE_ENROLLMENT_DRAFT_INTEGRATION_VALIDATION_RECEIPT`; the signed candidate and
`PRE_ENROLLMENT_DRAFT_INTEGRATION_FINAL_ATTESTATION` bind the final head,
receipt, evidence digest, signer, current-main observation, and initial Draft
identity.

The executor persists both typed evidence documents before its sole branch
push. An unwritable or exhausted output boundary therefore fails before the
irreversible mutation. Initial-head proof creation also consumes an opaque
commit-verification result binding the actual two-parent topology, tree,
signature format, and maintained signer; matching caller-authored attestation
fields alone are not verification.

This path is not ordinary sole-parent remediation and is not
`TWO_PARENT_READY_INTEGRATION`: it consumes no Ready authority, review budget,
remediation budget, recovery, or continuation. One invocation observes one
final current state, constructs and non-force-pushes at most one candidate,
verifies exact final head equality, and stops without retry or any merge,
review-request, Ready-transition, graph, issue, label, or lifecycle mutation.

Native genesis for a delivery still selected by this bootstrap family accepts
only the schema-1.1 typed initialization whose head is the exact live open
Draft PR head. This makes a competing ordinary genesis inadmissible between
the authenticated absence observation and branch push without granting the
bootstrap executor a journal mutation or reservation operation.

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

Version 1 exact adoption retains its provider-backed review-count semantics.
Version 2 adds one closed
`PRE_ENROLLMENT_REVIEW_BUDGET_CONSUMPTION_ADMISSION` mode for a previously
unenrolled delivery whose historical review-consumption provenance was not
persisted. The migration role signs a domain-separated admission binding the
exact open delivery, current head and tree, verified signature and validation
evidence, canonical provider chronology, complete intended state, and adoption
time. It conservatively consumes the single normal review budget; it does not
reconstruct a review, verdict, finding, reviewer, or GitHub
`ReviewSubmission`. Provider review observations and this admission are
disjoint modes, and supplying both fails closed. Remediation, Ready, exceptional
history, and every other state field remain independently observation-derived.

Version 3 adds the distinct
`SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION` source mode. It does
not reinterpret versions 1/2. Its sole authority is adoption source truth for an
exact signed, unenrolled OPEN Draft with unavailable commit-bound validation
companions and successful fresh current-policy safety validation. Historical
reviewed-state, receipt, and final-attestation bytes are never synthesized. The
historical final-attestation identity remains unavailable; PR prose cannot supply
it. The signed receipt trailer remains provenance, not the missing receipt.

The maintained issuer accepts only repository and issue selectors. Clean current
protected main selects the exact loss acknowledgment in
`policies/pre-enrollment-validation-evidence-loss.json`, the existing registry,
and the existing migration/adoption signer role. That record becomes an
authenticated acknowledgment only when accepted on protected main; issue prose,
caller-reported missing files and unsigned loss flags carry no authority. It is
exact-source policy, not an artifact store or another journal. The issuer
authenticates the live OPEN/Draft PR, head/tree/sole parent, accepted source
signature and exact trailer, complete stable feedback and provider chronology.
Provider reads are first converted by a pure, bounded representation-normalization
boundary into canonical typed facts; admission consumes only those facts and does
not repeat provider parsing.
The protected lifecycle journal must prove CURRENT and native admission absent.

Current safety executes the closed accepted-main
`PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_CURRENT_SAFETY` profile, not every later
repository regression. Its maintained assertions cover the applicable recovery
and adoption safety contract without requiring unrelated newer implementation
APIs. Normal repository Complete Validation remains unchanged for the delivery
that changes this policy.

Accepted-main commit authentication first observes the protected branch SHA,
then uses one fixed maintained provider projection containing only that exact
commit SHA and GitHub's boolean verification result. Projection occurs before
the unchanged 64 KiB bootstrap capture; the resulting external bytes still pass
duplicate-aware closed parsing and exact-SHA admission. The generic provider
transport, chronology acquisition and authenticated large Git-blob path retain
their existing distinct bounds.

The profile binds its version, harness Git blob/mode/size, command set and digest,
120-second bound, exact successful result and required invariant inventory.
Only `tests/pre-enrollment-current-safety.py` is projected into a disposable
execution copy. All non-test candidate files retain their exact parked bytes;
no implementation overlay, dual-version runtime or synthetic integration is
permitted. Historical tests do not supply assertion authority. The existing
isolated Python runner excludes environment paths and site initialization, and
the disposable tree rejects undeclared files, bytecode and symlinks. Source bytes are checked
independently of index flags before and after execution. Every captured source,
including resolved/outdated threads, replies, review submissions and conversation
comments, must match the accepted technical decision inventory. Blocking,
incomplete or changed decisions reject. This is current safety, not another
unrestricted review. Source, feedback or accepted-main drift invalidates live
verification. Fresh safety identity and historical receipt provenance are
separate bindings and must differ.

The existing version-1 admission binds this profile through its policy and
command-set digests, with `validated_tree_sha` still naming the parked tree.
Changed policy cannot authenticate previously signed bytes as evidence for the
new profile: live verification rederives these bindings and rejects drift.

The version-1 loss admission permits only review 1, remediation 2, Ready
transitions 0, Draft true, Ready false, no exceptional history and no Cycle 3.
The existing review-budget admission remains independently required for review
1; exactly two normalized `REMEDIATION_HEAD_OBSERVED` entries establish
remediation 2. Ordinary verified validation and the sealed loss source are
disjoint inputs: invalid or partially supplied historical evidence cannot
downgrade to loss mode.

The signed admission becomes immutable provenance in the version-3 adoption
proof and existing signed one-use adoption authorization. Enrollment rechecks
live absence and source facts, then uses existing protected publication/CAS
uniqueness to reject competing enrollment and replay. Historical proof
verification checks signatures and closed bindings without requiring CURRENT
to remain absent after enrollment. No new state, signer, counter, journal,
Ready permission or source-bootstrap authority is introduced. The #827 / PR #830
case is exercised hermetically; implementation does not enroll or mutate it.

Exact-state adoption reuses the maintained migration signer role, enrollment
uniqueness, protected publication journal, CAS, lifecycle identity and authority
digest conventions. Later transitions use the ordinary successor verifier, and
Ready integration consumes the same published prior-authority manifest/tag
boundary with the adopted tree, receipt, and adoption-time attestation bound by
the proof. Native deliveries cannot self-select adoption, a second enrollment
root remains forbidden, and adoption is not a lifecycle state, Recovery,
Continuation, or permission to cure ordinary ordering after the fact.

After an Exact-State-Adoption v3 delivery completes its first ordinary
Draft-to-Ready transition, prior-authority manifest schema `1.2` can normalize
that already-authenticated source into the same Ready-integration input without
reconstructing unavailable reviewed-state, validation-receipt, or final-
attestation bytes. The verifier reopens protected CURRENT and the enrollment
publication, independently verifies the v3 proof, loss and review-budget
admissions, exact signed sole-parent source, unchanged head/tree, one published
`DRAFT_TO_READY`, finite counters and empty exceptional histories, and requires
the canonical existing annotated-tag namespace and exact commit target. Both
bridge derivation and selection internally derive their executing tooling root,
authenticate its complete verifier package and policy blobs against one signed
protected-main commit, and reject mixed module origins. The distinct candidate
repository supplies only immutable Git objects and may legitimately contain
different implementation bytes. Protected main is rechecked during authority
composition so a main transition requires a fresh run. Schema `1.1` remains the
ordinary companion-backed form;
malformed or incomplete `1.1` input cannot fall through to `1.2`.

For a later head-changing ordinary successor, the immutable adoption proof
remains the genesis while the signed successor authority binds verifier-derived
current-head tree, receipt, final attestation, and source-evidence identity.
Prior-Ready verification authenticates those current facts and the unchanged
genesis chain; it never treats genesis evidence as evidence for a later head.

For an unchanged Ready delivery that predates evidence persistence, missing
historical package bytes do not become reconstructed evidence. One explicit
`READY_INTEGRATION_PRIOR_AUTHORITY` recovery may instead bind the exact signed
sole-parent head and tree, current protected lifecycle publication and complete
finite Ready history, historical receipt trailer and attestation digest as
provenance only, fresh complete feedback/validation facts, and one signed
bounded-use authorization. Unsigned facts are non-authoritative. The maintained
issuer derives protected-main policy, captures the complete resolved and
unresolved feedback universe, executes validation, and signs the full capture,
exact source-complete technical decisions, policy/command identity, and receipt.
The accepted signer and protected publication are the first trusted recovery
boundaries. The authorization is appended to the existing
protected lifecycle-publication journal without advancing CURRENT. Missing or
invalid supplied evidence never selects this path, and the published recovery
becomes stale if its bound lifecycle publication ceases to be CURRENT.

The Ready-integration verifier accepts either the ordinary complete historical
package or that independently verified protected recovery and normalizes both
to the same prior-Ready boundary. Recovery does not select current `main`, build
an integration commit, advance lifecycle state, classify late feedback, or
resolve a thread.

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
The same maintained bootstrap-source list contains one closed #776 / PR #779
pre-enrollment implementation admission. It binds the immutable source chain,
maintained signer policy, fixed action entrypoint/command, and accepted-main
validation command/result digests. It creates no lifecycle, publication,
CURRENT, Ready state, or candidate-tree authority; those remain downstream.
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
authorization. After that Recovery is consumed, `CONTINUATION_COMMIT_PUSHED`
may select only the existing `EXCEPTIONAL_CONTINUATION` transition when CURRENT
proves Continuation count zero and canonical current-head feedback/eligibility
proves the exact non-empty material finding/thread set. Its signed existing-family
authorization binds the PR, predecessor/resulting heads, reviewed-state,
stable-feedback and eligibility digests, and those exact identities. It preserves
`Draft=false`, Ready and all prior histories, requires fresh final-tree evidence,
requests no review, and cannot create Cycle 3. `Ready -> Draft` and any later
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

## Authenticated Ready/Draft execution

`scripts/secpal_pr_review/lifecycle_execution.py` is the maintained execution
boundary for the two existing user-authorized `DRAFT_TO_READY` and
`READY_TO_DRAFT` decisions. Its single-transition entry point accepts only the
repository, delivery issue, and canonical signed lifecycle-orchestration
authorization. It derives the PR,
head, operation, predecessor publication, lifecycle authority, signer, scope,
and intended successor from those authenticated authorities rather than caller
assertions.

This module owns bounded side-effect composition and final convergence because
orchestration intentionally owns policy decisions without mutation, lifecycle
authority owns state derivation, and lifecycle publication owns the protected
journal and CURRENT. Putting execution into any of those modules would combine
independent responsibilities. The executor therefore reuses all three and the
existing trusted `gh` executable/environment boundary; it adds no lifecycle
state machine, transition, journal, signer role, or persisted transaction state.
`NEW_PERMANENT_CONCEPT=NO`.

The closed observation cases are:

1. GitHub and CURRENT at the exact predecessor: mutate GitHub once.
2. GitHub at the target and CURRENT at the exact predecessor: publish the exact
   successor without replaying GitHub.
3. Both at the exact target: authenticate the historical transition and return
   success with zero writes.
4. CURRENT at the target and GitHub at the predecessor: fail closed.

All other states fail closed. A write is ordered
`GitHub mutation -> live target read-back -> exact CURRENT CAS publication ->
independent CURRENT read-back -> final GitHub/CURRENT convergence`. Immediately
before each write the executor reauthenticates the exact live PR, head, OPEN
state, CURRENT predecessor, signed authorization, and orchestration decision.

One narrower convergence case extends that boundary without adding an event or
recovery path. When GitHub already records the authorized Draft-to-Ready event
at H0, CURRENT is still its exact authenticated Draft predecessor, and one
independently authorized remediation commit has advanced the same Ready PR from
H0 directly to H1, the executor publishes the two existing successors in their
only valid order:

```text
CURRENT Draft @ H0
  -> DRAFT_TO_READY @ H0
  -> REMEDIATION_COMPLETED H0 -> H1
```

The path requires a complete GitHub timeline proving that Ready occurred while
H0 was the PR head, with no intervening or later Ready-to-Draft, force-push, or
additional commit. It separately re-verifies the exact one-use remediation
authorization and finding identities, verifier-sealed validation receipt and
final attestation, H1 tree, maintained signer, and sole-parent H1-to-H0 commit
topology. Ancestry alone supplies no authority. The executor derives both
states through the existing authority owner and publishes each existing
successor through the ordinary protected CAS boundary. The exact midpoint and
complete states are resumable and replay-safe; GitHub receives no duplicate
Ready write.

The maintained accepted-main entry point for that fixed shape is
`converge_pending_ready_head_advancement`. It accepts the two exact signed
authorizations and verifier-sealed remediation evidence directly; it is not a
mode of the single-transition entry point. The immutable #810 first-executor
bootstrap remains a closed historical bootstrap for its exact admitted source
and is intentionally not a dispatcher for later accepted-main capabilities.
Expanding that frozen admission would create new bootstrap authority rather
than make accepted-main code reachable.

This is autonomous convergence, not a new decision boundary, exactly when all
intermediate operations are already authenticated, the existing transition
order is unique, source lineage is exact, and the result equals current GitHub
truth. Mechanical lifecycle lag is not Exceptional Recovery; checkpoint
reordering grants no delivery authority; and authenticated head advancement
does not permit skipping a missing transition. Ambiguous chronology, a
Draft-valid source operation, competing source changes, or any non-exact
midpoint fails closed.

The GitHub write is the fixed non-interactive `gh pr ready` or
`gh pr ready --undo` form with an exact repository and PR. No executable, host,
GraphQL document, state assertion, or retry option is caller-controlled. Any
ambiguous GitHub result receives one live read: target continues, predecessor
stops incomplete, and anything else fails closed. Any ambiguous publication
receives one CURRENT read: the exact successor is complete, the exact
predecessor is publication-pending and resumable, and anything else fails.
Fresh invocation reconstructs progress solely from live GitHub and protected
CURRENT; it never creates another execution journal or transaction record.

Production lifecycle signing derives each required identity from the installed
policy role. The OS account may map that already accepted identity to one local
credential reference by adding a closed JSON value to the global Git key
`secpal.lifecycleSigningCredential`, for example:

```text
{"credential":"/absolute/local/key","identity":"accepted-role@example.test"}
```

The mapping is only credential selection, never trust policy. Duplicate,
malformed, relative SSH, unsupported-format, missing distinct-role, unusable,
and policy-mismatched credentials fail closed. An explicit role mapping takes
precedence over `user.signingkey`; the latter remains the compatible routine
default only for ordinary transition, authority, publication, and genesis
roles where those operations use the routine signer. Every produced signature
is verified against the selected role's
accepted policy credential before it is returned. The maintained legacy-
adoption bridge exposes neither caller-selected identity nor key path and
supplies the existing exact-state-adoption v2 admission, authorization, and
proof constructors without changing their domains or payload authority.

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

One accepted candidate uses zero full snapshots, one stable-feedback read, zero
hosted-CI or Required Check reads, one successful complete local validation,
one holistic audit per candidate, at most one signed remediation commit and ordinary push, and one
target-bound simple resolution pass. Package-2.1/2.2 snapshots remain available
only in explicit forensic mode.

The feedback-remediation helper has no polling, waiting, recursive review loop,
automatic late-feedback incorporation, review request, Ready transition, merge,
or auto-merge capability. The separate bounded provider observation described
above is available only to a currently authorized full delivery and never
observes unrelated hosted CI.
A correctable local error is repaired in the same invocation, and a read-only
failure may receive one bounded retry. Writes never retry; an unknown write
result stops with its exact operation identity.

On ordinary success, the normal success report contains only `RESULT`, `HEAD`,
`MUTATIONS`, `EVIDENCE`, relevant `LIFECYCLE` counters, `BLOCKER`, and
`NEXT DECISION`. Blockers, exceptional paths, and complex security decisions
retain the detailed evidence needed for safe diagnosis.

## Hosted CI authorization

GitHub-hosted CI is outside ordinary Polyscope and AI execution. A push, PR
creation, review-remediation request, repository convention, previous request,
or thread-resolution request does not authorize reading or summarizing hosted
checks.

Only a current user instruction that explicitly requests CI inspection, check
status, merge readiness, or merge authorization permits fresh operation-bound
CI reads. Provider-status observation is not authorization to observe unrelated
hosted CI. Merge remains explicitly current-user-authorized, including bounded
conditional authorization granted in that same instruction.

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
placeholder, and does not run later commands or retry the failed command on the
unchanged tree. That candidate is rejected. If the failure is diagnosed, the
correction stays inside current authority, no external mutation occurred, and
focused validation plus a repeated holistic audit cover a changed candidate,
the same invocation may perform one complete validation of that changed final
candidate. A successful complete validation is never repeated on an unchanged
tree. If that single corrected candidate also fails, stop without a third
candidate or attempt in the invocation. The fresh audit replaces the
invalidated audit for the rejected tree; it does not increment the existing
one-audit session counter. New authority is required only when the correction
crosses scope, recovery, or another genuine decision boundary.

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
`attest-validation --integration-evidence` and the closed version-1.1 or
version-1.2 `TWO_PARENT_READY_INTEGRATION` topology. Version 1.1 retains the
same-head reviewed snapshot. Version 1.2 requires and separately binds a
distinct reviewed predecessor so
an already-attested remediation successor can remain parent 1 without
requesting another unrestricted review. In that case the prior ordinary
receipt and final attestation must authenticate the exact reviewed-state and
feedback digests; an unrelated or caller-substituted snapshot fails closed.
The invocation also supplies the exact
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

Every newly produced Ready integration validation must supply
`--eligibility-evidence` with `--integration-evidence`. The receipt
binds both digests and binding emits the distinct version-1.2
`ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION`. The guarded
resolver accepts that kind only with the canonical integration artifact and
only after the integration-specific verifier authenticates the ordered parents,
tree, both trailers, reviewed state, expected signer, and eligibility. The
historical version-1.1 integration attestation remains valid for integration
authentication but cannot authorize resolution. Current production tooling
cannot mint another unbound version-1.1 integration attestation. Other
evidence-mode combinations remain closed.

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

Schema 1.1 is the mutually exclusive diagnostic-backed form of that same
Recovery family. It is available only for the maintained
`python-version-token-encoding/v1` material-security profile and independently
reproduces the exact defect against the authenticated prior Ready tree before
proving the sole permitted correction on the proposed tree. The artifact binds
CURRENT publication and lifecycle authority, exact head/tree identities,
finding and canonical reproduction-evidence digests, deterministic fixture and
command identity, fail-first and correction results, exhausted finite counters,
preserved Ready state, and an explicit empty thread list. Its signed one-use
authorization additionally binds the exact sole-parent successor. Provider
failure is not diagnostic authority, and this form grants no thread-resolution,
review-request, Ready/Draft, merge, or unrelated source-write authority. Schema
1.0 thread-backed bytes and semantics remain unchanged.

Maintained diagnostic Recovery code is authenticated as the exact
`scripts/*.py` inventory from one immutable protected-main commit. Each
installed regular file must preserve its accepted mode and raw Git blob OID;
symlinks, inventory drift, and substituted bytes fail closed. This reuses the
exact-source Git hashing boundary, so authenticated repository blobs do not pass
through or weaken the generic 64 KiB external-evidence transport bound.

The one post-Recovery source-changing sibling is
`READY_EXCEPTIONAL_CONTINUATION`. It binds the exact prior Ready head/tree,
frozen continuation tree, current-head material findings/threads, stable
feedback, eligibility, maintained source signer, preserved Ready and Recovery
histories, and Continuation `0 -> 1`. The normal signed sole-parent commit and
ordinary receipt/final attestation bind the artifact. The published historical
transition and signed orchestration authorization bind the resulting head
without introducing a circular commit hash. Recovery and Continuation artifacts
are distinct, mutually exclusive receipt modes and cannot authenticate each
other. Resulting-head feedback may differ only when a closed
Continuation-specific safety extension preserves every predecessor source,
authenticates the canonical provider request/result/review transport, and gives
every other successor-only source a complete maintained non-blocking
classification. Classification reuses the detached
`LATE_FEEDBACK_CLASSIFICATION` family and signer trust: version 1.2 binds the
predecessor/resulting Stable State digests, exact source identities and digests,
thread state, and independently established disposition before signing. Raw
caller labels and digests have no authority. Material, unclassified, unrelated,
spoofed, stale, or ambiguous growth blocks. Successor safety does not enter the
earlier source-correction authorization or resolver scope, and its verification
performs no provider request. A Continuation-bound resolver receives this
separate proof through `--exceptional-continuation-successor-safety`; the
immutable source authorization, receipt, attestation, and commit remain reusable.

Schema 1.1 extends that same one-use Continuation family for one candidate that
was rejected before publication. It requires unchanged exhausted Ready CURRENT
with Recovery consumed and Continuation unconsumed, an authenticated same-head
`PR_REBOUND`, the original and replacement PR identities, and independently
captured Stable Feedback for both PRs. The original-PR candidate must be a
signed, validated, sole-parent successor of CURRENT, remain unpublished, and
have complete exact-head provider acquisition plus signed version-1.3 material
classifications. Its original typed Continuation document is normalized,
cross-bound to the delivery, CURRENT tree, lifecycle, and source signer, and
bound by the candidate receipt and attestation. Validation policy and schema
come from a base proven in protected-main ancestry rather than the verifier's
checkout. Those classifications bind the rejected state, exact finding
sources, and `CANDIDATE_REJECTED_BEFORE_PUBLICATION`; they are diagnostic input
only. The signed correction authorization also binds both PRs, protected
CURRENT, the rejected head/tree/receipt/attestation, both Stable Feedback
states, exact material findings and sources, and the corrected sole-parent
head/tree. Fresh exact-head provider safety is still mandatory for the corrected
candidate, and any material or unclassified successor finding blocks
publication.

The same re-anchor authority permits the replacement PR to retain a newer base
only when the original base, replacement base, and independently observed live
protected-main head form one authenticated accepted-main lineage. The
replacement base is derived from its canonical Stable Feedback state; caller
base assertions have no authority. The exact immediate same-head `PR_REBOUND`
remains mandatory, and the protected lifecycle CURRENT must remain unchanged.
Provider Compare acquisition first normalizes one closed bounded observation;
a separate pure predicate admits only exact ancestor lineage. The durable
re-anchor projection binds the historical and replacement bases, while the
later live protected-main tip remains runtime verification and cannot change a
previously signed scope or digest. Legacy same-base re-anchor evidence keeps its
original projection and digest.

Rejected-successor safety schema 1.2 permits one narrower provider
representation: Codex may remove its predecessor direct-PR completion
`THUMBS_UP` reaction and add one replacement completion reaction while reviewing
the rejected candidate. The closed record names both reaction identities, the
fixed provider, and the fixed content, and must match complete terminal
exact-head Code and Security review transport. Its canonical digest binds the
PR, both Stable Feedback states, the rejected head, the full provider transport,
and the removal/replacement pair into the re-anchor projection and existing
signed Continuation authorization scope. Actor or content substitution, missing
or additional reaction churn, incomplete or nonterminal transport, wrong-head
or wrong-PR evidence, and replay remain rejected. Corrected-successor safety
schema 1.0 retains its historical clean Code/Security no-finding behavior and
predecessor preservation.

Corrected-successor safety schema 1.1 is the re-anchor-only alternative for one
terminal exact-head Codex Code Review containing suggestions. It authenticates
the exact review object, provider identity, reviewed commit, body digest,
terminal summary, Code/Security request comments, and the existing independently
terminal Security no-finding result. Completeness is derived from the canonical
Stable Feedback source inventory: every suggestion source must have an existing
signed version-1.2 invalid/disproven or informational/non-actionable successor
classification bound to the repository, PR, exact head, both Stable Feedback
states, exact finding content, and live thread state. A Code no-finding result
or completion reaction is incompatible with this representation. Missing,
additional, ambiguous, stale, cross-boundary, material, actionable, unsafe, or
unclassified findings remain blocking. The classification proves candidate
safety only and carries no thread-resolution or lifecycle-transition authority.

The re-anchored artifact carries no resolution-eligible thread identities. Old
threads remain owned by the original PR, and the resolver rejects schema 1.1
Continuation evidence outright. Clean or incomplete replacement-PR
rediscovery cannot erase the authenticated original-PR rejection, nominate a
tree, or grant cross-PR mutation. The rejected candidate never becomes CURRENT,
an ancestry root, or a lifecycle transition. Successful publication remains the
existing `EXCEPTIONAL_CONTINUATION` transition and consumes only its existing
`0 -> 1` counter.

The simple resolver first verifies the caller-captured reviewed-state digest,
successful validation attestation, actual local signed commit, and exact
per-thread eligibility manifest authenticated by the signed validation
receipt. A Recovery- or Continuation-bound ordinary attestation additionally
retains and passes `--delivery-issue` plus exactly one typed
evidence/authorization pair from the corresponding accepted lifecycle authority.
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

A schema-1.1 Ready-integration boundary is distinct from that special recovery.
It requires the exact original receipt alongside integration evidence and
proves that both receipt and attestation omit `eligibility_evidence_digest`.
The derived `NO_COMMIT_BOUND_READY_INTEGRATION_ELIGIBILITY` fact supplies no
thread authority. The existing source verifier authenticates the integration,
exact Stable Feedback derives origin, and the existing detached signed
classification/disposition chain supplies the only resolution authority.
Schema 1.1 alone remains rejected, and schema-1.2 commit-bound behavior is
unchanged.

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
receipt trailer, attestation, typed final-eligibility boundary, origin, and
accepted commit signature. That boundary is either the canonical manifest or
the maintained exact authenticated-absence record; a supplied invalid manifest
never falls back to absence. It proves the named thread absent from final
eligibility and derives its origin from authenticated final reviewed state:
`REVIEWED_BUT_INELIGIBLE` when present there, or `ABSENT_FROM_BOTH` when
absent. A target already in final eligibility is rejected, and original
eligibility is never replaced. It verifies that every eligible thread belongs
to the reviewed state and derives the actual
delivery signer fingerprint, reads that named thread twice, and signs the
classification with that same OS-account identity. The disposition creator
verifies the classification signature and exact live binding and computes its
digest internally. SSH and OpenPGP are supported.
The resolver independently repeats the final-delivery verification, verifies
both canonical artifacts and detached signatures against the derived signer,
and compares exact live head, thread, top-level comment node/database identity,
body digest, reply state, resolved/outdated state, classification, disposition,
technical-blocking flag, and guarded action before resolving. The closed path
accepts the canonical corrected/actionable, invalid/disproven, and
informational/non-actionable pairs for `REVIEWED_BUT_INELIGIBLE`, and retains
invalid/disproven or informational/non-actionable for `ABSENT_FROM_BOTH`.
Every pair requires `technically_blocking=false`.
No caller-selected origin, other classification or disposition, or technical
blocker is accepted. The path consumes no review/remediation counter and has
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
