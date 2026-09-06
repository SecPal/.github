<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

## Pull Request Evidence

### `secpal-pr-review.py`

Captures deterministic, thread-aware GitHub pull-request evidence and verifies
immutable evidence and local Git state through a strict read-only command
boundary. `verify-evidence` supports open, closed, and merged snapshots;
`verify-gate` reuses that evidence path and additionally evaluates current
open-PR merge readiness only when the current user instruction explicitly asks
for readiness or merge evaluation. Neither command authorizes merge. Canonical JSON is
the authority; Markdown is an escaped derived view. The helper performs no
review request, reaction, reply, thread resolution, push, or merge operation.

See [Deterministic PR State and Evidence Layer](../docs/secpal-pr-review-state-layer.md)
for schemas, bounded pagination, signature and required-check semantics, safe
outputs, commands, and Package 2.1 non-goals.

### `secpal-pr-review-actions.py`

Validates deterministic Package-2.2 mutation plans and applies at most one
explicitly selected, anchor-bound reaction, inline evidence reply, or eligible
thread resolution. The helper performs one current-target idempotency read even
in audit mode; a write additionally requires `--apply`. Every plan must match the
checked-in repository registry and binds its finding, target, immutable target
state, counters, and recorded mutation identities before a write. Its exact
command and endpoint allowlists provide no review-request, Ready-transition,
generic API, Git-write, label/issue, merge, or auto-merge capability, and failures
are never retried. It independently verifies Package-2.1 evidence before every
operation. Its legacy forensic/readiness resolutions are permitted only when
the current user instruction explicitly requests readiness or merge evaluation;
they additionally run all registered local validations and
re-check the complete live thread comment set, applicable required-check rules,
current base, effective check target, and required-check outcomes, then repeat
the PR-wide feedback and exact target reads. Reply targets include their exact
parent node identity. Registry validation permits only the required direct
tools, checked-in scripts, and approved project-script forms before any command
runs. PR-wide feedback must match across two complete bounded projections.
Resolution plans reject
unrecorded already-resolved targets, canonical-reference cycles, unsafe
canonical dispositions, actionable fixes without commit and test proof, and
operations whose evidence does not match their logical finding. Their initial
and final heads must also encode exactly one new linear commit per recorded
signed push, or no commit movement for a no-push session.

`attest-validation` also exposes a separately selected version-1.1
`TWO_PARENT_READY_INTEGRATION` evidence path. It authenticates exactly one
signed two-parent candidate whose first parent is the prior Ready delivery head
and whose second parent is the explicitly authorized live current registered
`main` tip. The versioned manifest consumes the maintained protected-journal
lifecycle publication for parent 1, including its persistent identity, current
authority digest, and finite exceptional history. Ordinary typed integration
uses `HEAD_ADVANCED` and preserves both exceptional counters exactly; it does
not consume recovery or continuation budget.

The fresh tree receipt, integration-evidence
trailer, final attestation, expected signer, stable-feedback and eligibility
digests, unchanged lifecycle counters, and exact bounded manual tree delta all
fail closed together. Clean merge-tree output admits no delta. Conflict-bearing
output binds the exact conflict paths and requires each to be explicitly
changed or deleted, with no extra paths or retained text conflict markers. This
does not relax the ordinary sole-parent path, create or push an integration,
change Ready state, read post-push checks, or authorize merge automation.
Historical receipt reconstruction reads the registry blob from the immutable
prior delivery commit rather than applying a later registry to older evidence.
When exact thread resolution is required on the integration head,
`attest-validation` may additionally consume the canonical eligibility
artifact. That closed combination emits the version-1.2
`ELIGIBILITY_BOUND_READY_INTEGRATION_VALIDATION_ATTESTATION`; its receipt and
attestation bind the same eligibility digest. Historical version-1.1
integration attestations remain valid for their original integration purpose
but are not thread-resolution authority.

Successful verification of either supported Ready-integration attestation version
returns the existing verifier-sealed current-head validation evidence only after
the actual integration commit signature and signer identity have passed the
canonical signature verifier. The immutable private authority is bound to the
exact returned object identity; copying, replacing, reconstructing, or mutating
its nested seal cannot authenticate another value. The canonical source digest
retains its historical binding to the complete normalized integration package,
including delivery, topology, current-main, receipt, reviewed-state, expected
signer, kind, and version identities; actual signer authentication is the
additional precondition for issuing that compatible sealed result.
Exact-state-adopted `HEAD_ADVANCED` may consume it, but all independent lifecycle
authorization and publication preconditions remain mandatory.

The late-feedback boundary also supports one exact accepted-main
`AUTHENTICATED_FINAL_ELIGIBILITY_ABSENCE` recovery for `SecPal/.github`
issue #810 / PR #821. The complete detached late-authority tuple selects late
mode. Within that mode, omitting the final eligibility path selects that policy
record; the verifier then requires the exact zero-thread reviewed state, final
head and tree, receipt and attestation digests, delivery signer, and actual
omission of `eligibility_evidence_digest` from both reconstructed receipt and
attestation. It creates no eligibility manifest. A supplied final eligibility
path always uses the ordinary manifest verifier, so malformed, stale, or missing
supplied evidence cannot downgrade to absence recovery. Final eligibility
evidence outside late mode is rejected.

Classification schemas `1.0` and `1.1` select the invalid/disproven and
informational/non-actionable decisions respectively. Disposition schemas bind
both decision and evidence mode: `1.0`/`1.2` are manifest-backed invalid/info,
while `1.1`/`1.3` are authenticated-absence invalid/info. Cross-wrapping those
semantic pairs is rejected.

Parent 1 additionally requires a closed prior-authority manifest authenticated
by a signed annotated tag and independently verified ordinary receipt, final
attestation, tree, and signer. The receipt identities must agree end to end.
The mutable tag ref is resolved once, and every tag target, signature, signer,
trailer, and diagnostic check uses the resulting immutable annotated-tag OID.
OpenPGP signing subkeys are accepted only through their authenticated configured
primary fingerprint. Its lifecycle identity, Ready state, and counters
must match the integration evidence. When creating the integration receipt, the
command performs one trusted GitHub read and requires the live open Ready PR
head and registered target-base SHA to equal the two authorized parents; caller-
supplied `observed_sha` cannot substitute for that read.

After an explicitly authenticated cycle-limit blocker, a separate user
authorization may select `--exceptional-recovery-evidence` with exact recovery
issue/authorization selectors and eligibility evidence. The closed artifact
binds the prior Ready head/tree, new tree, exact reviewed findings/threads,
`review=1/1`, `remediation=2/2`, no Cycle 3, and unchanged Ready state. Its
digest is carried by the ordinary single-parent receipt and attestation; it is
not a third remediation cycle or a reusable recovery loop.

### `secpal-resolve-fixed-threads.py`

Resolves only explicitly named review threads after their findings have already
been evaluated, fixed where necessary, and validated. The supplied reviewed-state
capture must match the caller-provided captured state digest, and a successful
final attestation must bind that reviewed state to the exact fix commit. A raw
validation receipt for an unchanged head cannot authorize a resolution
mutation because the pre-existing commit does not authenticate that receipt.
The resolver verifies that evidence against the actual local commit tree,
signature, origin, and, for a new fix commit, its parent and receipt trailer. A
version-1.2 eligibility-bound Ready-integration attestation is instead routed
through the integration-specific verifier with `--integration-evidence`; the
resolver authenticates its exact ordered parents, tree, both evidence trailers,
expected signer, and eligibility digest before normalizing the resolution
anchor. It never routes an integration artifact through the sole-parent path. A
separate eligibility manifest must cover every requested thread exactly and
bind its allowed classification/disposition and finding evidence to the
reviewed state. Its canonical digest must be authenticated by the signed
validation receipt and final attestation, so it cannot be created or changed
after validation. Together they bind the operation to the caller-provided PR
head, the complete original ordered target set, and reviewed target-comment
identities, digests, and resolution state. An exact original target whose
reviewed state was unresolved may be classified as already satisfied when its
live state is resolved and every other binding still matches; that authenticated
postcondition produces no write. An unresolved target also retains the ordinary
guarded mutation path when its outdated state is exact or changes only from
authenticated reviewed `false` to live `true`, provided the accepted source-fix
authority, PR and head, thread and comment identities, bodies and replies,
eligibility, classification, disposition, and every other binding remain exact.
This compatibility does not normalize stale targets: `true` to `false`, missing
or non-boolean outdated state, and every other difference fail closed. A
Recovery-bound ordinary attestation also retains and passes the existing
`--delivery-issue`, `--exceptional-recovery-evidence`, and
`--exceptional-recovery-authorization` artifacts. Ordinary non-Recovery and
Ready-integration invocations omit that tuple. The shared Recovery verifier may
authenticate only the installed lifecycle-publication journal protection; it
does not grant delivery-PR branch-protection or merge-readiness authority. After
one initial complete target read, the resolver requires two more equal complete target
projections immediately before each write or successful already-resolved
report, and keeps thread resolution separate from CI and merge-readiness
decisions. It accepts
only canonical registry repositories, enforces their shared API, thread, and
comment limits, preflights every known read/write cost, uses the trusted GitHub
CLI boundary, and reports partial failure without retrying a write.

This is the default resolver after review remediation pushes. A push, PR
creation, prior request, repository convention, remediation request, or
thread-resolution request never authorizes hosted-CI observation. Local
validation and push hooks remain required. Hosted checks may be read only for a
current explicit CI/readiness request, using one bounded current-state read with
no polling, waiting, sleeping, or automatic repetition.

For an exact technically non-blocking target absent from authenticated final
eligibility and observed on the unchanged delivery head,
`secpal-create-late-classification.py` verifies the existing final delivery
evidence and derives `REVIEWED_BUT_INELIGIBLE` or `ABSENT_FROM_BOTH` from
authenticated final reviewed state. It accepts
`INFORMATIONAL + NON_ACTIONABLE` for either origin; the existing
`INVALID_FALSE_OR_MISLEADING + DISPROVEN_WITH_EVIDENCE` pair remains accepted
only for `ABSENT_FROM_BOTH`. All require `technically_blocking=false`. The
creator captures only the named live thread and authenticates the explicit
classification decision. Then
`secpal-create-late-disposition.py` verifies that decision, computes its digest
internally, and creates a canonical detached SSH/OpenPGP-signed artifact without
a delivery commit. Ordinary final-delivery evidence remains the default. A
canonical eligibility-bound Ready-integration source is supplied to both
creators and the resolver with `--integration-evidence`; all three route it
through the maintained integration-specific verifier, and authenticated
attestation shape selects the evidence family. The resolver consumes both signed artifacts through a
separate explicit eligibility path,
requires the actual detached signer to match the verified final delivery
signer, and binds the delivery issue, PR, unchanged head/tree, receipt and
attestation, exact thread and top-level comment identities, body and reply
state, classification, disposition, technical-blocking flag, and guarded
resolution action. It cannot select arbitrary threads or authorize any other
GitHub mutation.

This authenticated reviewed-state/eligibility boundary is what “post-push”
denotes in the resolution lifecycle. It does not use or claim a cryptographic
GitHub wall-clock push-order proof.

See [Simple PR Thread Resolution](../docs/simple-pr-thread-resolution.md) for
the bounded safety contract and usage.

### `install-secpal-pr-review-skill.sh`

After Package 2.2 is merged, installs the repository-owned skill as a direct
canonical link under `$HOME/.agents/skills/`. The installer is idempotent,
refuses non-symlink targets and unexpected links, and requires `--repair` before
replacing a wrong link. It compares canonical absolute link text without
GNU-specific `readlink` options and never modifies unrelated user configuration.

See [Finite SecPal PR review workflow](../docs/secpal-pr-review-workflow.md) for
explicit invocation, state limits, classification, guarded action ordering,
registry decisions, recovery, and post-merge rollout prerequisites.

### `secpal_pr_review/lifecycle_authority.py`

Defines the reusable, orchestration-independent delivery-lifecycle authority.
Version 1.0 uses the maintained canonical JSON/digest functions and closed,
domain-separated initialization, transition authorization, authority snapshot,
and evidence-bundle schemas. A registry-anchored initialization binds ordinary
delivery receipt/attestation identity and deterministically derives the
persistent lifecycle and canonical Draft genesis. Every later snapshot is
derived by independently verifying the complete predecessor and event chains;
callers cannot provide counters, Ready history, exceptional history, or a new
lifecycle identity as resulting authority.

`verify_lifecycle_authority` accepts only canonical serialized lifecycle
evidence. It loads signer roles, SSH keys, OpenPGP fingerprints, formats, and
one initialization root per enrolled delivery issue from the installed
maintained repository registry. The same policy independently selects the exact
current terminal authority digest, PR, and head, so same-head stale prefixes
cannot nominate themselves as current. Empty anchors remain valid before
explicit adoption; replacement PRs continue the original root through
`PR_REBOUND`. The verifier invokes concrete `ssh-keygen`/GnuPG verification.
Duplicate fields, noncanonical JSON, consumer-preparsed mappings, and Git OIDs
other than exactly 40 or 64 lowercase hexadecimal characters fail closed.
`lifecycle_authority_binding` derives a stable digest and exact verified facts
for explicit adoption by later receipts or attestations. Existing delivery
validation does not call this module and continues to use the ordinary
one-parent evidence path.

The same enrollment family also defines the versioned exact-state-adoption
proof. It authenticates normalized pre-enrollment observations and one exact
finite current state under a separately signed one-use authorization, while
keeping the ordinary event list empty and starting cryptographic lifecycle
authority at the real adoption time. The proof uses the maintained adoption
signer and existing publication/successor machinery; it does not weaken native
genesis or event-derived state verification and is not available as an ordinary
delivery escape hatch.
External facts enter proof assembly only through the canonical verifier-derived
boundary: the existing receipt/final-attestation verifier derives source
evidence, signature admission authenticates the commit, and observation
normalization derives history provenance. Later head-changing successors bind
fresh verified current-head evidence in the signed ordinary authority while the
original adoption proof remains immutable.

Existing exact-adoption version 1 remains the provider-review mode. Version 2
adds a closed, domain-separated
`PRE_ENROLLMENT_REVIEW_BUDGET_CONSUMPTION_ADMISSION`, signed by the existing
migration role, for zero-provider-review deliveries whose earlier normal review
consumption was not persistently authenticated. The admission consumes exactly
one finite review budget and binds one open delivery, head, tree, validation
evidence set, provider chronology, intended state, and adoption timestamp. It
does not claim a historical review result or add verdict/finding evidence.
Mixed provider-review/admission inputs, replay into another context, resets,
and using the admission to derive remediation or Ready state fail closed.
The lifecycle-authority suite is an unconditional registered validation command.

### `secpal_pr_review/validation_evidence_loss.py`

Owns the version-1
`SECPAL_PRE_ENROLLMENT_VALIDATION_EVIDENCE_LOSS_ADMISSION` consumed only by
exact-state-adoption version 3. Existing adoption versions 1/2 and ordinary
commit-bound validation remain unchanged. Its semantic contract is the
exact-state-adoption section of `docs/secpal-pr-review-workflow.md`.

The maintained entry points are
`lifecycle_authority.issue_pre_enrollment_validation_evidence_loss_admission(repository, delivery_issue)`
and
`lifecycle_authority.verify_pre_enrollment_validation_evidence_loss_admission(serialized)`.
Issuance requires clean current protected main, not candidate-local policy.
There is no caller-selected registry, command list, signer, source checkout,
successful result, feedback snapshot, loss flag or CURRENT selector. Public
verification authenticates signed bytes and reacquires current source, policy,
feedback and absence facts without rerunning complete validation. The migration
signature authenticates the issuer's execution facts.

Acquisition owns provider/Git reads and isolated registered validation.
`_normalize_provider_representations` purely converts bounded external values
to canonical typed facts; `_admit_observation` consumes only those facts, and
`_assemble_source_facts` only assembles admitted facts. These responsibilities
serve one exact-source contract, not a general source executor. Dependency
preparation is fixed `npm ci --ignore-scripts --no-audit --no-fund` with a temporary
HOME, closed credential-free environment and 600-second bound. Accepted-current
test, script and package harness bytes are verified against protected main and
overlaid on a disposable copy of the immutable source before the existing
registered runner executes; historical harness bytes never become policy.

`current_safety.receipt_digest` is the current execution identity under
`secpal.pre-enrollment-current-safety/v1`, **not** an ordinary validation receipt.
The target-shaped regression retains the previously observed divergent receipt
identities; production derives its own current execution identity. No historical
package bytes or unauthenticated final-attestation identity are reconstructed.

The sealed source enters existing external-evidence authentication with
`validation_evidence=None` and a separately authenticated review-budget admission.
Passing both source modes rejects. The existing adoption proof and enrollment
publication supply durable provenance and the single use. Issuance alone neither
enrolls nor authorizes review, remediation, Ready, thread resolution or recovery.
The #787 bootstrap and existing role credential selection remain separate.

### `secpal_pr_review/bootstrap_source_admission.py`

Authenticates exact immutable implementation sources through one accepted-main
`BOOTSTRAP_SOURCE_ADMISSION` family. Its executable
`FIRST_READY_EXECUTOR_BOOTSTRAP_SOURCE` subtype is the exact PR #812 source
maintained for #810's first Ready-executor bootstrap. Accepted-main policy fixes the source
head, tree, parent, receipt, final attestation, signer, implementation path,
entrypoint, purpose, and source PR base repository/ref. Live provider reads emit
a representation which is purely normalized before a separate pure admission
step. Evidence files use the maintained bounded regular-file reader. The
verifier fetches that object into a private detached tree, independently reuses
the ordinary receipt/final-attestation verifier, and keeps candidate imports
inside that tree. Its child launcher reports only closed diagnostic identities;
it never exposes child stderr or exception text.

The ordinary executable-source path is unchanged: when a historical evidence
directory is supplied, reviewed state, the byte-semantic receipt reconstructed
from the immutable delivery registry, and the final attestation must all verify.
Invalid supplied evidence fails immediately and never falls back. The historical
receipt reconstruction used by Ready integration remains integration-only and
does not admit this ordinary source.

For the exact #810 / PR #812 source only, an absent evidence directory selects
one closed `BOOTSTRAP_SOURCE_EVIDENCE_LOSS_RECOVERY` sub-record in the existing
accepted-main `bootstrap_source_admissions` policy. It states
`HISTORICAL_EVIDENCE_UNAVAILABLE_BUT_EXACT_RECOVERY_AUTHORIZED`, binds the
unchanged source-admission digest, and carries distinct exact-source recovery
validation and technical/security-gate digests. The verifier re-authenticates
the signed head, tree, sole parent, receipt trailer, signer, implementation blob,
path, entrypoint, 40 diagnostic raise sites, non-self-admission property, live
open Draft PR, `main` base, and the exact canonical stable-feedback inventory
accepted by the recovery gate. That inventory digest covers review submissions
and their commit association, conversation comments, review threads, ordered
thread comments and replies, actors, body digests, reactions, and
resolved/outdated state through the maintained bounded pagination and duplicate
identity checks. A new `COMMENTED` review body or same-count feedback
substitution therefore fails even when the aggregate review decision remains
unchanged; blocking aggregate review decisions also continue to fail. It also
reconstructs the immutable source's
15-command registry only to authenticate the fresh recovery-validation command
set. It does not synthesize, reconstruct, or claim byte identity for lost
`reviewed-state.json`, `validation-receipt.json`, or `final-attestation.json`.
The maintained historical receipt and final-attestation digests remain
provenance facts, not claims that the unavailable raw artifacts were freshly
verified.

The closed `PR_REVIEW_EVIDENCE_HELPER_SOURCE` subtype admits only the exact PR
PR #819 `scripts/secpal-pr-review.py` blob needed by #818. It has no entrypoint,
launcher, import, or execution authority. The public verifier selects this
admission only from the exact protected-main registry object, through a closed
independent `gh`/`git` boundary with concurrent bounded stdout/stderr capture,
timeout/overflow termination and reap, and rejection of partial output. A
candidate-local registry or caller-selected executable, path, ref, OID, policy,
or policy-source value cannot establish the admission. The admitted historical
commit, tree, parent, signature, validation
evidence, path, and blob remain immutable after a lawful PR-head advance. The
live PR independently retains its repository, number, base, state, and exact
Ready/Draft binding, while one bounded current-head blob observation proves
that the candidate still consumes the exact admitted helper bytes. That observation
atomically re-reads the PR head with the blob selected at the initially
authenticated head, so concurrent advancement fails closed. The mutable
current PR head is never treated as the immutable admitted source identity.

Both source paths return a sealed `VerifiedBootstrapSource` with an explicit
historical evidence status. The #812-only evidence-loss recovery does not apply
to the byte-only #819 subtype. Historical P2.1 remains rooted at commit
`833eef2afc063ae777e7e2b64b2f252e3fe1e49e` and helper blob
`c0e5dc15879010339cc08b6e2fbcb1ff51f4d4e2`. Source admission alone performs no
GitHub mutation, lifecycle publication, CURRENT change, genesis operation, or
work-graph mutation; the admitted executor still requires #810's separate
signed one-use lifecycle-transition authorization.

### `secpal_pr_review/lifecycle_orchestration.py`

Authenticates the independently selected CURRENT lifecycle publication before
selecting one bounded lifecycle action. It consumes the canonical work-graph
classification and keeps technical and mechanical blocking independent. PR
replacement selects `PR_REBOUND`; an explicitly authorized exhausted Ready
recovery selects `EXCEPTIONAL_RECOVERY`, while bounded normal remediation
selects `REMEDIATION_COMPLETED`; both preserve Ready. Explicit
Ready/Draft changes require their exact separately reasoned authorization.
Every user-controlled orchestration decision consumes canonical signed evidence
bound to the exact CURRENT publication, authority, PR, head, operation, reason,
and scope. Caller-constructed mappings have no authority.

Review objects, CI observations, reopen events, validated Ready integrations,
and completed feedback assessments are evidence-only observations. They never
increment/reset counters, request another review, transition Draft/Ready, or
create a recursive processing pass. A separately authorized additional review
first appends `ADDITIONAL_REVIEW_AUTHORIZATION_CONSUMED`, then permits one
bounded assessment and stops without consuming the single normal unrestricted-
review counter. Publishing that same-head transition makes replay stale while
preserving Ready and every finite counter.

For `NON_BLOCKING_FOLLOWUP`, the orchestrator consumes the canonical #673
classification and the #689 exact live follow-up verifier. The guarded resolver
continues to authenticate commit-bound eligibility and reports the resolution
as `SAFELY_DISPOSITIONED_TRACKED`, never fixed, implemented, or completed. The
orchestration suite is an unconditional registered validation command.

### `secpal_pr_review/lifecycle_execution.py`

Executes the maintained authenticated Ready/Draft transitions and supplies the
local signer bridge used by lifecycle production paths. Signer identities come
only from installed lifecycle policy. The OS account may add bounded global Git
configuration values under `secpal.lifecycleSigningCredential`, each containing
exactly a JSON `identity` and `credential` reference. The identity must already
be selected by a policy role; the local mapping grants no authority.

Explicit mappings override the compatible routine `user.signingkey` default.
Distinct legacy-adoption signing has no routine-key fallback. SSH references
must be normalized absolute paths, OpenPGP references must be full
fingerprints, and every detached result is cryptographically verified against
the accepted policy credential before becoming a `Signer` result. Selection
keeps the existing closed non-interactive environment and does not use an SSH
agent, inspect private-key contents, search for keys, or mutate Git config.

### `secpal_pr_review/lifecycle_publication.py`

Publishes lifecycle authority on one protected, append-only global journal
branch outside delivery trees. Native enrollment requires the maintained #750
root, full authenticated history, and an independently signed native-genesis
admission already reachable in protected journal ancestry. Admission is a
separate typed journal operation that selects no CURRENT terminal. A genuinely
pre-#750 lifecycle instead
uses exactly one dedicated-role-signed `LEGACY_ADOPTION_CHECKPOINT`, explicitly
marking its imported baseline as a migration trust decision rather than
retroactively invented proof. Every successor after either root uses normal
issue #750 transition derivation.

The legacy-adoption credential is cryptographically distinct from ordinary,
lifecycle-transition, and publication credentials, with overlap rejected while
loading maintained policy. Enrollment stops exactly at the checkpoint terminal;
post-checkpoint state is accepted only as a later journal advancement.

Static policy fixes the GitHub remote, exact
`refs/heads/secpal-lifecycle-publications` branch, live ruleset ID, deletion and
non-fast-forward prohibitions, publication signer role, and migration signer
role. The verifier authenticates that protection, resolves the branch once, and
uses immutable ancestry to select the newest event for each lifecycle. Lease
CAS prevents concurrent writer races; live branch protection independently
prevents rollback and deletion.

New native delivery publication is a two-CAS sequence: admission first, then
enrollment after re-verifying the reachable admission. A branch-local static
anchor cannot publish. A separate closed historical-compatibility registry
binds every retained pre-#774 exception to its repository, issue, PR, initial
head, initialization digest, proof mode, exact enrollment object OID, and signed
publication digest. A new publication carrying the same initialization cannot
inherit that exception. One closed issue 774 repair allowance admits the exact
existing issue 736 initialization after
independently verifying its signed initialization and original enrollment; the
repair appends to rather than rewrites journal history. See
[`docs/native-lifecycle-genesis-admission.md`](../docs/native-lifecycle-genesis-admission.md).

All transport uses a controlled temporary bare repository and closed Git
environment. The public reader accepts repository/issue expectations but no
repository path, remote, branch, signer set, key, verifier callback, migration
checkpoint, or caller-selected terminal digest. Empty journals remain valid
before adoption. The publication suite is an unconditional registered
validation command.

Native enrollment initially satisfies #750's maintained current-tip boundary.
Once enrolled, a private publication-only verifier authenticates later complete
successor chains from #750 while protected journal ancestry selects CURRENT. The
ordinary #750 public verifier remains strict, and callers receive no flag or
alternate trust input that can bypass its current-tip check.

## Work Graph

### `secpal-work-graph.py`

Read-only resolution of the GitHub-native SecPal work graph. Semantics:
[docs/work-graph-contract.md](../docs/work-graph-contract.md) — the tool derives
its results from that contract and defines none of its own.

```bash
scripts/secpal-work-graph.py show          SecPal/.github#665
scripts/secpal-work-graph.py validate      SecPal/.github#665
scripts/secpal-work-graph.py ready         SecPal/.github#665
scripts/secpal-work-graph.py next          SecPal/.github#665 --executor <login>
scripts/secpal-work-graph.py validate-issue SecPal/.github#669
```

A scope root or issue is given as `owner/repo#number`, as an issue URL, or as a
bare number together with `--repo owner/repo`. Output is deterministic JSON by
default; `--format text` renders the same resolved model for humans.

Options: `--gh` (path to the `gh` executable), `--timeout` (per-request seconds),
`--max-nodes` (issues read per invocation). `next` resolves its executor identity
from `--executor`, and otherwise from the authenticated `gh` identity.

Exit codes: `0` success, `1` structural findings reported (`validate`), issue not
`READY` (`validate-issue`), or `NEXT` inputs not fully observable (`next`), `2`
invalid input, `3` GitHub or parser failure. Both canonical `NEXT` no-selection
results are ordinary answers and exit `0`.

Requirements: an authenticated `gh` CLI, Python 3, and `npm ci` so the
`markdown-it` parser used for structural acceptance-criteria detection is
present. The tool reads through `gh api graphql` only, performs no mutation, and
persists no state.

### `secpal-dependabot-manifest-coverage.mjs`

Deterministically discovers tracked dependency manifests and validates either
the shared `MANIFEST_COVERAGE` assertion or the separate `CADENCE_POLICY`
assertion. Ecosystem knowledge and upstream provenance come exclusively from
`policies/dependabot-manifest-catalog-v1.json`. Exact repository exceptions and
module classifications are usable only from a separately supplied trusted
protected-history root; subject-branch review strings are never authority.

```bash
node scripts/secpal-dependabot-manifest-coverage.mjs coverage \
  --repository SecPal/example --default-branch main \
  --trusted-policy-root /path/to/protected-baseline --format json
node scripts/secpal-dependabot-manifest-coverage.mjs cadence \
  --repository SecPal/example --format text
```

See
[`docs/dependabot-manifest-coverage.md`](../docs/dependabot-manifest-coverage.md)
for discovery, anti-drift, matching, exception, reporting, and reusable-workflow
semantics.

### `secpal-pr-advisory.py`

Reports #674 delivery-PR findings and, with `--enforce`, applies the #735 hard
work-graph boundary. It reads GitHub's native closing-issue relationships,
delegates every graph predicate to the canonical resolver, and reports the
owning issue, graph state, violated rule, exact graph fact, and an action.
Hard findings exit with status 1 and emit a GitHub error; incomplete or invalid
evidence fails closed separately.
Resolver-provided readiness reasons and execution claims drive the corresponding
advisories. The gate also compares the PR's exact `Part of` line with the native
parent already present in that resolver snapshot. That field is extracted by
the maintained Markdown parser only from top-level paragraph metadata, so
quoted, fenced, commented, and container examples are not authoritative.

```bash
GH_TOKEN="$(gh auth token)" \
  scripts/secpal-pr-advisory.py --repo SecPal/.github --pr 800 --enforce
```

An explicit assessment may be supplied with `--assessment FILE`. Its closed
`secpal-pr-advisory/v1` document contains `observations`, `feedback`,
`lifecycle_claims`, and `review_smells`. Judgment observations are explicit
review evidence, never inferred from line, test, or mutation counts. Feedback
is validated by the existing #673 classifier, so #692 lifecycle/disposition
semantics remain authoritative. The gate never interprets those counts as
standalone failures and never mutates graph, PR, lifecycle, review, or check
state. The hard set is limited to execution readiness, complete and sole
primary-delivery claim evidence, one closing leaf, native-parent references,
direct non-leaf closure, and blocked delivery. Independent-responsibility
classification remains a mandatory section-7.2 review judgment: the report
names that obligation explicitly but does not falsely claim source-code
inference can enforce it. Other #674 judgment findings remain advisory,
preserving #736's separate evidence-architecture responsibility.

The required hard result is named `Work-Graph PR Gate`, distinct from the
preserved `Work-Graph PR Advisory` context. Mutable issue body/state events run
`secpal-work-graph-gate-refresh.py`, which first publishes `pending` for the
bounded set of open PR heads and then recomputes the same canonical gate.
GitHub requires both a same-name Actions check and commit status when both
exist, so a prior head-bound success cannot hide the refreshed result. Native
sub-issue and dependency mutations that GitHub Actions cannot trigger directly
consume this same refresh through the maintained graph-replan mutation
boundary. Candidate overflow, unreadable graph evidence, authentication
failure, or publication failure stops fail closed; no polling is used.

## Validation Scripts

### `check-domains.sh`

Enforces the SecPal `secpal.*` namespace by classification. The script greps text files
in the working tree (via `grep -r --include=...`, so untracked files matching
the include patterns are inspected too), extracts each matching hostname-like
token independently, and flags tokens that fall outside the approved set
of public/external hosts (`secpal.app`, `apk.secpal.app`, `secpal.io`),
development/preview hosts (`secpal.dev`, `api.secpal.dev`, `app.secpal.dev`, the
`preview.secpal.dev` base, plus arbitrary `*.preview.secpal.dev` previews), the
identifier-only `io.secpal.*` reverse-DNS namespace,
and the exact private internal logical database service identity
`db.secpal.internal`. It also surfaces
`api.secpal.app`, the deprecated `.app` web host, so callers cannot reintroduce
it as an active host.

The `io.secpal.*` allowance applies only in explicit reverse-DNS identifier
contexts such as an application ID, package, namespace, or bundle identifier.
It does not approve those values as URLs or public hosts. The Android ID
`app.secpal` remains a valid architecture value, but it is outside this
scanner's intentionally `secpal.*`-seeded matcher and is not claimed as an
enforced value here.

`db.secpal.internal` is an approved logical PostgreSQL connection/TLS service
identity, not a public web host or DNS-routing commitment. This exact allowance
does **not** approve arbitrary `*.secpal[.]internal` names; all other
`secpal[.]internal` identities remain fail-closed unless a separate explicit
architecture decision adds one.

**Active namespace policy versus historical evidence:**

- Every `secpal.*` token on an active/current policy surface is classified
  independently and fail-closed. An approved token on the same source line
  cannot mask a forbidden token.
- The validator's small exact-path historical-evidence registry permits only
  proven archived/superseded records to quote historical identifiers. It is not
  a wildcard path rule, a documentation/ADR exemption, or domain approval;
  placing the same identifier in an ordinary current file still fails.
- Regression fixtures that need forbidden values construct their final token at
  runtime. This keeps the tracked test source subject to the active scanner
  while ensuring temporary fixtures exercise the real complete value.

**Scope (intentional limit):**

- The match regex is `secpal\.[A-Za-z0-9.-]+`, so only `secpal.*` strings are
  ever inspected. Non-`secpal` domains are out of scope by design — even when
  they belong to SecPal (e.g. `guardguide.de`).
- SecPal-owned external hosts such as `guardguide.de` (managed via
  SecPal/.github#483) are governed by their own repository policy guards and
  are not first-class entries here. Adding them to this allowlist would be
  inert because the matcher never sees them.
- Treat the banner's "Forbidden" list as "forbidden `secpal.*` variants",
  not "every non-SecPal domain on the internet".
- The scan protects the gitignored agent scratch directory `.context/` with
  two complementary layers (SecPal/.github#489). Layer one is the
  **grep exclusion** `--exclude-dir=".context"`, which skips every directory
  named exactly `.context/` at any depth (alongside `.git/`, `node_modules/`,
  and `vendor/`). Polyscope-managed workspaces use `.context/` to pass
  throwaway files between agents and the `gh` CLI (PR body drafts, scratch
  notes, etc.) that never reach CI, so the local gate must not flag them
  either. Layer two is the **tracking-aware guard**: before grep runs, the
  script invokes `git ls-files` on `.context/` and exits non-zero if any
  path under `.context/` is actually tracked by git. Because `--exclude-dir`
  is git-tracking-unaware, this guard closes the `git add --force` bypass
  review flagged on this PR — force-tracked `.context/` files would
  otherwise be visible to CI but silently ignored locally. The guard is a
  no-op outside a git working tree (e.g. in the throwaway `mktemp`
  workspaces the regression tests use), so it does not interfere with
  packaging or distribution scenarios. Violations in any tracked path
  (inside or outside `.context/`) still fail the gate.

**Usage:**

```bash
bash scripts/check-domains.sh
```

**Exit Codes:**

- `0`: No forbidden `secpal.*` variants or deprecated `.app` web-host usages
- `1`: One or more violations found

### `audit-closed-epics.sh`

Legacy migration-compatibility helper that compares Epic checklist mirrors with
current issue state. It is report-only; the canonical resolver and GitHub-native
relationships remain authoritative.

**Usage:**

```bash
# Audit the full SecPal workspace set
bash scripts/audit-closed-epics.sh

# Audit a smaller scope
bash scripts/audit-closed-epics.sh --org SecPal --repo .github --repo api
```

**What It Checks:**

1. Searches for open and closed Epic issues by label and title
2. Parses checklist-linked child issues from each epic body
3. Ignores PR references so merged PR numbers are not mistaken for issues
4. Reports:
   - open child issues in closed epics
   - checked items that point to non-closed issues
   - stale unchecked checklist items whose child issues are already closed

**Exit Codes:**

- `0`: No checklist issues found
- `1`: One or more checklist issues found
- `2`: Usage or dependency error

### `check-system-requirements.sh`

Validates the local toolchain baseline for the managed SecPal repositories,
including the Android-specific Java/SDK requirements that direct Gradle and
Polyscope-provisioned workspaces need.

**Usage:**

```bash
bash scripts/check-system-requirements.sh
bash scripts/check-system-requirements.sh --repo=android
```

**What It Checks For Android:**

1. Node.js 22 and `npm`
2. Java 21 plus `javac`
3. Android command-line tools via `sdkmanager`
4. Android platform-tools via `adb`
5. An SDK path under `$HOME/Android/Sdk` or via `ANDROID_SDK_ROOT` / `ANDROID_HOME`
6. Android local dependencies such as TypeScript, Vite, Vitest, and ESLint
7. Presence of the committed native `android/` project directory

**Exit Codes:**

- `0`: All critical requirements met
- `1`: One or more critical requirements missing

### `check-openapi-verified-endpoints.mjs`

Regression guard that fails if `docs/openapi.yaml` in any SecPal repo omits an
operation from the verified-endpoint allowlist. The allowlist is defined inside
the script and reflects operations that have confirmed feature-test coverage.

**Usage:**

```bash
node scripts/check-openapi-verified-endpoints.mjs <path-to-openapi.yaml>
```

**Exit Codes:**

- `0`: All required operations are present
- `1`: One or more required operations are missing
- `2`: Usage or file-read error

### `validate-ai-instructions.sh`

Validates the independent `AGENTS.md` runtime baseline, Copilot review profile,
and focused instruction overlays across all repositories.

**Usage:**

```bash
# In any repository (.github, api, frontend, contracts)
./scripts/validate-ai-instructions.sh
```

**Tests Performed:**

1. **File Existence**

   - Checks for `AGENTS.md`
   - Checks for the independent `.github/copilot-instructions.md` review profile

2. **REUSE Compliance**

   - Validates `AGENTS.md` REUSE metadata
   - Requires the complete repository-policy expression in inline SPDX
     metadata or a valid `.license` sidecar and rejects conflicting or duplicate
     declarations across both sources
   - Requires plain `AGPL-3.0-or-later` for managed baselines and preserves only
     the API repository's intentional `CC0-1.0` baseline
   - Preserves exact deliberate `AGPL-3.0-or-later`, `Apache-2.0`, `CC0-1.0`,
     or `MIT` expressions on focused overlays
   - Rejects the obsolete expression
     `AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution`

3. **Markdown Linting**

   - Runs markdownlint-cli on instructions
   - Uses the repo-pinned `markdownlint-cli` installed by `npm ci`
   - Does not download a fallback tool

4. **UTF-8 Markdown Structure**

   - Rejects unreadable, empty, malformed UTF-8, or heading-less files

5. **Focused Overlay Structure**

   - Requires opening and closing frontmatter delimiters
   - Requires non-empty `name` and `applyTo` values

6. **Discovery Size**
   - Ensures `AGENTS.md` stays below the 32 KiB runtime discovery ceiling

The validator does not require textual equality, mirror declarations, copied
overlay bodies, inheritance markers, or arbitrary policy keywords.

**Exit Codes:**

- `0`: All tests passed
- `1`: One or more tests failed

**Example Output:**

```
=========================================
SecPal AI Instructions Validation
=========================================

Repository Type: api

✓ required instruction files exist
✓ AGENTS.md is readable UTF-8 Markdown
✓ copilot-instructions.md is readable UTF-8 Markdown
✓ AGENTS.md has REUSE license
✓ copilot-instructions.md has REUSE license
✓ instruction Markdown passes lint
✓ instruction overlays include valid frontmatter
✓ AGENTS.md stays under runtime discovery size limit

=========================================
Summary
=========================================
Total Tests: 8
Passed: 8
Failed: 0

✓ All tests passed!
```

**CI Integration:**

Automatically runs in GitHub Actions:

- On push to `main` (when instruction files change)
- On pull requests (when instruction files change)
- Manual trigger via `workflow_dispatch`

See `.github/workflows/validate-ai-instructions.yml`

**Dependencies:**

- `bash` (required)
- `grep` (required)
- `npm ci` in `SecPal/.github` (installs the pinned `markdownlint-cli` and `prettier` CLIs)
- `ruby` (optional, only for the legacy YAML syntax check)

**Repository Identity:**

Canonical GitHub and Polyscope callers supply trusted repository identity via
`GITHUB_REPOSITORY` or `SECPAL_REPOSITORY_NAME`. Content-based detection remains
a local compatibility fallback and does not select production policy when a
trusted identity is available. Repository-path mode clears ambient identity and
derives each target independently. The legacy `REPO_TYPE` hint cannot select
the strict API policy without the exact `secpal/api` manifest:

- **org**: `.github` repository (org-wide instructions)
- **api**: SecPal API (has Composer package name `secpal/api`)
- **frontend**: React frontend or Android wrapper (has `package.json` with `vite`)
- **website**: Astro landing page (has `astro.config.mjs`)
- **contracts**: OpenAPI contracts (has `package.json` with `openapi` or `docs/openapi.yaml`)

### `sync-required-checks.sh`

Builds and applies the repository-specific required status-check payloads for
the SecPal application repositories.

**Usage:**

```bash
# Inspect the payload for one repository without writing to GitHub
bash scripts/sync-required-checks.sh --repo guardguide.de --print-payload | jq

# Apply the configured payload to one repository
bash scripts/sync-required-checks.sh --repo api --apply

# Apply the configured payloads to every managed repository
bash scripts/sync-required-checks.sh --apply
```

**Managed Repositories:**

- `.github`
- `api`
- `frontend`
- `contracts`
- `android`
- `secpal.app`
- `GuardGuide`
- `guardguide.de`

**What It Does:**

1. Defines the required status-check contexts per repository in one manifest
2. Builds the exact JSON payload GitHub expects for branch protection updates
3. Applies the payload through `gh api` using `--input` so booleans and arrays stay typed correctly
4. Keeps the live branch-protection baseline repeatable after workflow or context drift

**Exit Codes:**

- `0`: Payload printed or sync applied successfully
- `2`: Usage error, unknown repository, or missing dependency

### `audit-polyscope-state.py`

Audits the local Polyscope runtime state for repository/clone drift, stale
worktree directories, clone-local config hygiene, and over-retained SQLite
backups.

**Usage:**

```bash
# Audit the real local Polyscope state
python3 scripts/audit-polyscope-state.py

# Audit a custom Polyscope home and print JSON findings
python3 scripts/audit-polyscope-state.py --polyscope-home /tmp/test-polyscope --json
```

**What It Checks:**

1. Repository IDs in `polyscope.db` that do not have a matching clone root
2. Clone roots that no longer belong to any registered repository
3. Clone subdirectories that are not valid Git worktrees
4. Valid Git worktrees that are not registered in the `worktrees` table
5. Registered worktrees whose on-disk path no longer exists
6. Worktree rows referencing a `repo_id` that is missing from `repositories`
7. Registered worktrees missing clone-local `polyscope.local.json`, drifting from the repo-root config, or where Git would still track `polyscope.local.json` (the check uses `git check-ignore` so commented (`#`), negated (`!`), or look-alike (`.bak`) entries in `info/exclude` are not mistaken for effective coverage, and per-worktree gitdirs of linked worktrees are followed automatically)
8. `polyscope.db.backup-*` files beyond the configured retention count

**Exit Codes:**

- `0`: No findings
- `1`: One or more findings detected
- `2`: Usage error or missing dependency/state

### `reap-polyscope-clones.py`

Conservatively reclaims orphaned Polyscope repository clone roots and
unregistered worktree directories. It protects every repository root and every
active `worktrees.path` currently registered in `polyscope.db`, waits seven days
by default, and skips candidates with lock files or active processes. An active
worktree at a clone-root level is never scanned for children; otherwise, only
its immediate non-hidden child directories can be worktree candidates.
Immediately before deletion the reaper revalidates the database while holding a
write-reservation transaction and atomically detaches the candidate through a
pinned, non-symlink parent-directory handle, so concurrent registration or a
parent-path replacement cannot redirect recursive deletion. Quarantines live at
the clone-root level so a later run can finish cleanup after an interruption.
The reaper revalidates candidates after process inspection before measuring
dry-run storage, and rejects symlinks and paths outside the configured clone
root.

**Usage:**

```bash
# Inspect eligible orphan roots and potential reclaimed space
python3 scripts/reap-polyscope-clones.py --dry-run

# Reap an isolated fixture or non-default Polyscope location
python3 scripts/reap-polyscope-clones.py --polyscope-home /tmp/polyscope --clone-root /tmp/polyscope/clones --grace-period 14d
```

The rollout installer enables `polyscope-clone-reaper.timer`, which runs the
reaper daily after startup. The reaper prints reclaimed bytes and supports
`--json` for operational reporting.

### `install-polyscope-rollout.sh`

Installs the unprivileged SecPal Polyscope rollout systemd units that keep
registered workspace clones, prompts, and preview config in sync. Run this
from the workspace root when `setup-hooks.sh` reports a managed repo as
**skipped (missing directory)** so the rollout-managed workspace can sync back
to the expected repository set.

**Usage:**

```bash
POLYSCOPE_SERVER_SCOPE=system bash .github/scripts/install-polyscope-rollout.sh
```

Run `install-polyscope-system-components.sh` first. This installer remains
unprivileged, requires the invoking account to be `secpal`, and verifies the
exact fixed-helper capability:

`sudo -k -n /usr/local/libexec/secpal-polyscope-nginx-apply --check`

The credential reset ensures the check proves the exact `NOPASSWD` rule rather
than a cached interactive sudo timestamp. It never tests generic sudo access,
rejects helper-path overrides, and exits before writing user units when the
fixed helper, fixed manifest path, system server drop-in, or exact
authorization is unavailable. The helper check validates the installed
root-owned bundle independently of the current manifest and advertises
`manifest_schema=2`; the unprivileged producer refuses to publish unless that
capability is present on the same fixed helper used for activation.
Environment-selected helper paths cannot authorize publication. This permits
consumer-first schema upgrades and allows a malformed active manifest to be
replaced without leaving Nginx on an unreadable manifest. Both system- and
user-scope server startup hooks skip repository config and database
synchronization; they perform only the Nginx convergence needed before the
service reports ready. If the full provisioner already holds the shared lock,
the startup hook exits successfully because that in-flight provisioner performs
the same final Nginx convergence. User-scope startup also receives the exact
sudo binary validated by the installer. Startup and routine refreshes use the
same configured clone root and provision lock as the full provisioner. A
system-scope installation accepts only the exact reviewed nonblocking startup
hook from the privileged component installer. Routine instruction/config
synchronization refreshes Nginx without reprovisioning every worktree;
provisioning remains owned by its path/timer service. The path unit deliberately
ignores the broad SQLite WAL stream so ordinary Polyscope activity cannot create
a provisioning loop; the main database, generated configs, and periodic timer
remain convergence inputs.

`--source-script` accepts a custom rollout implementation only as part of a
complete source bundle: the script must be executable, have the constrained
`polyscope_nginx.py` library and executable nginx helper beside it, and have an
executable `validate-ai-instructions.sh` sibling plus the canonical js-yaml
verifier with the committed npm validator dependencies installed. The installer
loads the pinned parser and verifies its required API before any installation
writes, then watches the runtime files and npm lock state for rollout changes
and dependency-install recovery.

After installation, the user-level `polyscope-rollout-sync.service` and
`polyscope-worktree-provision.service` units take care of provisioning new
managed repositories automatically when the canonical repo list changes. Both
the provision path and the three-minute fallback timer are enabled. The
provisioner reads only active `worktrees` registrations from `polyscope.db`,
resolves them beneath the matching repository clone root, and never scans an
unregistered clone as a setup candidate. The physical hash directory remains
the database's authoritative deletion path. Stable aliases are direct sibling
symlinks recorded in a strict per-repository registry; after official deletion
removes the physical path and registration, the next database-triggered
reconciliation removes only those recorded broken aliases.

On the canonical host, `--provision-worktrees` execution always includes Nginx
refresh even when an older installed unit does not yet contain
`--refresh-nginx`. Registered API previews receive two managed user services,
one scheduler and one combined queue worker. The services inherit the
installer-controlled tool `PATH`, resolve database credentials at process start
through the rollout wrapper, restart on failure, disappear when their worktree
registration is removed, and must produce a scheduler heartbeat before new
preview access is granted. Failed runtime-owner activation or heartbeat checks
revoke any access retained from an earlier successful provision. Stale services
for removed registrations are still pruned when another worktree fails canonical
instruction or routine ACL reconciliation. They are also restarted when the
worktree revision, dirty tracked code, untracked source metadata, or
source/worktree environment metadata changes. The corresponding Polyscope run
actions remain available for explicit diagnostics and do not autostart while
the managed services own the runtime. Noncanonical clone-root or database
installations instead keep those actions autostarted because no persistent
systemd owner is managed there. A failed reconciliation preserves existing units
only for still-registered physical worktrees; units belonging to removed
registrations remain eligible for pruning. Stale unit files are removed only
after systemd confirms that their services stopped successfully; a failure
preserves that unit without blocking later independent stale-unit cleanup.
Desired unit names are validated before cleanup starts, unreadable contents plus
ownership or permission drift are replaced, and independent cleanup and
activation failures are reported together. Routine preview ACL reconciliation
likewise attempts every unregistered physical worktree before reporting any
individual denial or repository-integrity failures. The paired daily
`polyscope-clone-reaper.timer` removes only aged orphan clone roots after checking
the live database allowlist, locks, and processes.

Every generated repository setup sequence starts with the validation-only
`--validate-instruction-worktree` command and explicit repository name inside
one strict shell entry. Cached setup definitions without that identity argument
remain compatible during rollout convergence by resolving the repository from
the worktree's active Polyscope database registration. The installed user
service exports the configured workspace root to those cached commands, so
nondefault installations retain the same managed-source identity boundary.
Missing, ambiguous, and unmanaged registrations fail closed instead of trusting
ambient identity or
mutable worktree manifests. The entry groups the complete native setup with
fail-fast semantics, so validation or any later command failure prevents every
remaining npm, Composer, `.env`, database, migration, seed, build, or repository
setup command. The external provisioner applies the same canonical contract
before its local configuration, hook, alias, setup, and marker writes.

The worktree provision service waits three seconds before each activation to
coalesce SQLite event bursts and takes a process-shared lock before provisioning.
Its 15-minute start budget leaves the provisioner time to record scheduler
readiness failures and perform final ACL/runtime cleanup before systemd ends the
oneshot.
The path and fallback timer both target that serialized service. Five starts per
ten seconds cannot be exhausted by the three-second activations, while genuine
service failures remain visible. A deliberate user-installer convergence clears
only historical failed state for the provision path and service before enabling
the new unit contract; it does not hide later failures.

### `install-polyscope-system-components.sh`

Installs only the root-owned Polyscope system boundary: the constrained nginx
helper and renderer bundle, two exact sudoers command forms, and the system
Polyscope server drop-in. Review the script, then run it interactively:

```bash
sudo -k
sudo .github/scripts/install-polyscope-system-components.sh
```

The host must provide `/usr/bin/setfacl` from its `acl` package before
activation. The installer checks this prerequisite before writing any system
component and exits with an actionable error when it is unavailable.

The installer resolves `node` before writing the system drop-in, verifies that
the `secpal` service account can execute it, and adds its directory to the
service `PATH`. If root's environment cannot discover a user-managed Node.js
installation, pass its absolute path explicitly:

```bash
sudo .github/scripts/install-polyscope-system-components.sh \
  --node-bin /home/secpal/.local/share/node/bin/node
```

The administrator enters the password only at the terminal prompt. The script
validates sudoers syntax before activation, writes fixed root-owned targets
atomically, and restores the previous components if activation fails. It does
not authorize shells, Python, `systemctl`, file utilities, or user-selected
paths through passwordless sudo.

`DESTDIR=/path scripts/install-polyscope-system-components.sh --stage-only`
renders a deterministic packaging fixture without root or a local `secpal`
account. Its UID 1000 systemd value is for validation only; a real installation
always resolves the target host's `secpal` UID and an executable Node.js path
before activation. Packaging tests may pass `--node-bin` to render the intended
service `PATH` without inspecting the target account.

Before activation, the installer verifies the executable canonical rollout and
validator source bundle, committed lockfile, and installed pinned Markdown and
YAML dependencies under `/home/secpal/code/SecPal/.github/`. The parser must
resolve and expose the required loading API to the `secpal` service account.
The system drop-in executes that source directly, so a fresh installation does
not depend on the user-local rollout link created during the following
unprivileged installation step.

The installed `/usr/local/libexec/secpal-polyscope-nginx-apply` accepts only no
arguments (apply) or `--check` (non-mutating boundary check). It reads the fixed
mode-`0600`, `secpal`-owned JSON manifest, rejects links, unsafe ownership,
unknown fields, non-loopback upstreams, invalid ports, and unsafe repository
identifiers, then renders one fixed nginx target internally. The exact
root-owned manifest library is checked before it is imported. Activation is
atomic; `nginx -t` precedes reload, and validation or reload failure restores
the prior configuration. Root may invoke the helper directly; invocations
carrying sudo identity are accepted only from `secpal` with its exact UID.

When the managed repository set changes, rerun this privileged installer before
the unprivileged rollout installer to replace the root-owned renderer contract.
During a staged upgrade, an older installed renderer can retain a syntactic
route for a retired repository. The live rollout supplies only the exact fixed
tombstone required by that older contract and fails closed if the tombstone's
clone-root path exists, so the compatibility route cannot serve content. The
privileged reinstall removes the obsolete content mapping from generated nginx
configuration. The retired hostname prefix remains reserved solely as an
explicit `404` boundary so it cannot be reinterpreted as a generic workspace.

After both installation steps, verify the steady state:

```bash
sudo -k -n /usr/local/libexec/secpal-polyscope-nginx-apply --check
systemctl --user is-active polyscope-rollout-sync.path
systemctl --user is-active polyscope-worktree-provision.path
systemctl --user is-active polyscope-worktree-provision.timer
systemctl --user is-active polyscope-clone-reaper.timer
```

### `setup-hooks.sh`

Installs pre-commit and commit-msg hooks across every managed SecPal repo
discovered next to the `.github` checkout. It also retires legacy
SecPal-managed full-preflight `pre-push` symlinks without touching custom hooks.

**Behavior:**

- Repos that are **missing on disk** are surfaced as a soft warning (separate
  summary line) and the script still exits `0` when every other repo's hooks
  installed cleanly. Run `.github/scripts/install-polyscope-rollout.sh` (or
  sync via Polyscope) to recover the rollout-managed workspace state.
- Managed repo paths that exist but are **not directories** are treated as real
  failures because they indicate a corrupted workspace layout, not a repo that
  simply has not been synced yet.
- Real failures in `setup-pre-commit.sh` or the commit-msg symlink still mark
  the repo as failed and exit `1`.

**Usage:**

```bash
bash .github/setup-hooks.sh
```

## Adding New Scripts

### `secpal-vulnerability-reevaluation.py`

Pure verification and adaptation boundaries for exact OCI index/platform
identity, authoritative Syft SPDX association, vendor-native Grype/Trivy
evidence, database identity/freshness, trusted reviewed-VEX checkout bytes, and
the versioned re-evaluation run envelope. It rejects noncanonical credentialed
repository paths outside the authenticated caller's exact GHCR namespace and
re-derives trusted policy output plus complete required-operation health from
raw evidence before issue mutation. Its `list-vex` command provides the single
fail-closed regular-file enumeration used by every reviewed-VEX workflow path;
`verify-vex` binds declared repository, ancestor commit, document path, bytes,
and digest to the authenticated checkout. External registry/scanner operations
remain in the reusable workflow.

### `secpal-vulnerability-triage.py`

Validates the run envelope and normalized policy result, then plans or delivers
caller-scoped deterministic GitHub issue updates. It searches every exact-subject
lookup key, retains authenticated historical alias keys on unique updates, fails
closed on ambiguous matches, reconciles healthy inverse transitions, and
maintains stable stale-health alerts without reimplementing vulnerability
policy.

When adding new scripts:

1. Include SPDX headers — either inline in the file or via a `.license` sidecar (both are valid for REUSE compliance)
2. For shell scripts, make executable: `chmod +x scripts/your-script.sh`; Node `.mjs` scripts run via `node` and do not require `+x`
3. Document usage in this README
4. Add CI workflow if appropriate
5. Test across all 4 repositories

## License

All scripts use MIT License unless otherwise specified.
See individual `.license` files for details.
