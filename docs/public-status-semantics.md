<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Public Status And Truth Contract

## Status and authority

Canonical. This document is the single organization-wide contract for what
SecPal may publicly claim about project state and which evidence makes such a
claim admissible. It operationalizes the public-truth boundary in the
[Product and Public Positioning Contract](product-positioning.md); it does not
replace that higher-level product-positioning authority.

This is a documentation and governance contract, not an architecture decision
record, a roadmap, or mandatory marketing copy. It consumes rather than
redefines:

- the [Work-Graph and Engineering-Governance Contract](work-graph-contract.md)
  for native work state and evidence classes;
- the
  [Evidence and External-System Architecture Contract](evidence-architecture-contract.md)
  for evidence-pipeline and external-representation semantics;
- the [ADR index](adr/README.md) and individual ADRs for architecture status and
  refinement or supersession; and
- repository-specific source, test, release, deployment, and operational
  evidence for the implementation or environment being described.

The primary invariant is:

> Public wording MUST NOT promote weaker, narrower, older, indirect, or
> differently scoped evidence into a stronger current claim.

Public prose does not need to expose raw engineering state. It does need enough
scope and qualification to remain true.

## 1. Claim model, not maturity ladder

A public status statement combines five concerns:

1. **Claim class** — which question the statement answers.
2. **Authority and evidence** — who owns that answer and what proves it.
3. **Scope** — the subject, version or ref, environment, and seam concerned.
4. **Currentness** — whether the evidence still describes the claimed state.
5. **Permitted inference** — what that evidence does and does not establish.

The claim classes below are independent dimensions, not stages of one lifecycle.
Several may truthfully coexist or change independently. For example, an
Accepted Architecture claim can coexist with an older source implementation, a
development deployment, a production deployment, and scoped real-system
verification, without any of those facts establishing Production Operation.
Planned and Active Implementation describe work; they are not product-maturity
levels.

There is therefore no global ordering such as `planned -> implemented ->
deployed -> production`. “Strongest supportable claim” means the most specific
claim supported **within the relevant claim class and scope**, not the highest
position on a universal scale.

### Evidence scope rule

> Evidence proves only the subject, version or ref, environment, seam, and time
> context it actually exercised.

Public wording need not mechanically print that five-part scope. It MUST expose
the parts needed to avoid a materially broader inference. One route test cannot
become API completeness; one provider run cannot become universal provider
support; one development deployment cannot become production operation; and one
production deployment cannot become production operation merely because the
artifact is present. One historical success cannot become current support.

## 2. Public claim vocabulary

The following matrix is a navigation aid. The detailed rules after it are
normative.

| Claim class                         | Question answered                                                           | Underlying authority                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Product Direction                   | What does SecPal deliberately intend to pursue or include?                  | Current positioning or explicit product decision                                      |
| Planned / Tracked Work              | Is there a current explicit plan or delivery contract?                      | Owning planning source; native GitHub graph and target contract for graph-backed work |
| Active Implementation               | Is the delivery actually being executed now?                                | Current execution evidence; canonical `ACTIVE` for work-graph-governed work           |
| Implemented in Source               | Does the supported source contain the delivered implementation?             | Authoritative supported branch/ref plus contract-appropriate evidence                 |
| Deployed to Development / Test      | Is an identified artifact actually running in a non-production environment? | Current environment, deployment, release, and artifact evidence                       |
| Production Deployment               | Is an identified supported artifact currently deployed in production?       | Current production environment, deployment, release, and artifact evidence            |
| Operationally / Externally Verified | Was a named real seam, collaborator, or operational path exercised?         | Admissible scoped real evidence under the canonical evidence contracts                |
| Production Operation                | Is the actual supported production path deployed and operating in scope?    | Current production deployment and operating evidence                                  |
| Accepted Architecture               | Which architecture decision is currently binding?                           | ADR index and individual ADR status and relationships                                 |
| Qualification / PoC / Exploration   | What candidate or hypothesis is being evaluated?                            | Owning evaluation contract and its bounded evidence                                   |
| Historical / Superseded             | What was once true or binding but no longer establishes current state?      | Preserved historical evidence and current successor/status authority                  |

### 2.1 Product Direction

**Meaning and authority.** A deliberate current direction is supported by the
canonical positioning contract or another explicit current product decision.
Speculative discussion alone is insufficient.

**Minimum evidence.** A current, identifiable decision authority states the
direction and its intended scope. Public wording MAY say that SecPal “is being
built as”, “is intended to include”, or “is exploring a product direction” as
the authority permits.

**Does not imply.** Product Direction does not establish a roadmap commitment,
active work, delivery sequence or date, implementation, or completeness.

**Change and downgrade.** If the decision becomes undecided, narrower, or
obsolete, narrow or remove the current-direction wording. Preserve earlier
wording as historical where it remains useful.

### 2.2 Planned / Tracked Work

**Meaning and authority.** A current explicit plan or delivery contract exists
in its owning planning source. For graph-backed engineering work, GitHub-native
issue data and the target node's contract are authoritative as delegated to the
work-graph contract.

**Minimum evidence.** The authoritative source is current, identifies the work,
and genuinely states intent to deliver or track it. Public wording MAY use
“planned”, “tracked”, or “intended work” with appropriate scope.

**Does not imply.** An open issue proves only that it is open. Neither an open
issue, assignee, board position, roadmap display position, sibling order, nor old
pull-request activity proves Active Implementation, proximity to completion, or
delivery.

**Change and downgrade.** If the plan is withdrawn, closed as not planned,
replaced, or narrowed, remove, historicalize, or narrow the claim. If execution
stops but tracked intent remains, Active Implementation may cease while Planned
/ Tracked Work remains true.

### 2.3 Active Implementation

**Meaning and authority.** Current authoritative execution evidence shows that
the delivery is actually being executed. For work governed by the SecPal work
graph, `ACTIVE` means exactly what the work-graph contract currently defines;
this contract creates no parallel test.

**Minimum evidence.** A current valid execution claim or other execution
authority appropriate to the owning process identifies the work being executed.
Public wording MAY say “currently being implemented” or “in active
implementation” only for that scope.

**Does not imply.** Open, assigned, `READY`, prioritized, or ordered work is not
thereby active. Active execution does not prove that the work is complete,
merged, deployed, verified externally, or production operating.

**Change and downgrade.** When the execution claim ends, expires, becomes
blocked, or otherwise ceases to satisfy its authority, public wording MUST stop
implying current execution. It may become Planned / Tracked Work if that claim
still has support; no universal fallback applies.

### 2.4 Implemented in Source

**Meaning and authority.** The current supported source contains the delivered
implementation at the stated contract boundary.

**Minimum evidence.** Normally this requires merged implementation on the
authoritative supported branch or ref, evidence appropriate to its delivery
contract using the work-graph evidence classes, and confirmation that current
source still contains and supports it. Public wording SHOULD prefer the precise
phrase “implemented in the current source” and retain any partial or bounded
scope.

**Does not imply.** A merged pull request alone does not establish deployment,
real-system verification, production readiness or operation, legal compliance,
or capability beyond the delivered contract. Native `DONE` proves completed
closure of the node, subject to the work-graph contract's delivery rules; it
does not expand that node's evidence scope.

**Change and downgrade.** Removal, replacement, loss of support, or material
divergence between the evidence ref and current source ends or narrows the
current claim. The former implementation may remain Historical.

### 2.5 Deployed to Development / Test

**Meaning and authority.** A specific implementation or artifact is actually
deployed to an identified development, test, staging, qualification, or other
non-production environment.

**Minimum evidence.** Current deployment records, environment observations,
artifact or release identity, and equivalent authoritative evidence MUST
identify enough context to distinguish source availability from a running
deployment. Public wording SHOULD name the material environment, such as
“deployed to the development environment”.

**Does not imply.** Non-production deployment does not establish production
deployment or support, equal assurance across all non-production environments,
qualification of unrelated seams, broad readiness, or Production Operation.

**Change and downgrade.** When the deployment is removed, replaced, inaccessible,
or no longer matches the claimed artifact or environment, remove or
historicalize this claim. Implemented in Source can remain independently true.

### 2.6 Production Deployment

**Meaning and authority.** An identified supported implementation or artifact
is deployed or installed in an identified production environment. This answers
whether the artifact is present in production, not whether it is currently
operating correctly.

**Minimum evidence.** Current authoritative deployment and environment evidence
MUST establish the production environment identity, the deployed artifact,
release, or ref identity where material, and that the deployment is currently
present. The evidence must distinguish the deployment from development, test,
staging, qualification, or a merely production-like configuration. Public
wording MAY say “deployed to production”, “the production environment currently
has [artifact or release] deployed”, or equivalent scoped factual wording.

**Does not imply.** Production Deployment does not establish Production
Operation, service health, successful request handling, complete runtime
functionality, Operationally / Externally Verified status, production
readiness, broad supportability, security assurance, or legal or compliance
status.

**Change and downgrade.** Remove or narrow the current claim when the artifact
is removed, replaced, no longer identifiable, no longer in the claimed
production environment, no longer supported for the claimed scope, or
contradicted by newer authoritative deployment evidence. A stopped, unhealthy,
failing, or temporarily unobservable service does not by itself erase a
still-provable Production Deployment claim. If deployment evidence also loses
currentness, the attributable former deployment may remain Historical.

### 2.7 Operationally / Externally Verified

**Meaning and authority.** A specifically identified behavior, seam,
integration, provider representation, runtime or deployment path, recovery
operation, or comparable real-system contract has been exercised using
admissible real evidence.

**Minimum evidence.** Evidence MUST satisfy the applicable integration or real
evidence class in the work-graph contract and the representation,
responsibility, and admission rules in the evidence-architecture contract. It
must remain attributable to the exercised version/ref, environment, seam, and
time context. Public wording MAY say “verified against”, “operationally verified
for”, or “validated on” followed by the material scope.

**Does not imply.** Repository-authored fixtures prove repository behavior, not
what an external system emits. Mocks prove assumptions, not a real seam. Hosted
CI can prove real behavior only for the actual seam and environment exercised.
One real success does not prove unrelated behavior, the whole product, or
production readiness.

**Change and downgrade.** If the exercised path, collaborator, representation,
version, or environment is no longer current, qualify the evidence as
Historical or make a narrower still-current claim. If source evidence remains,
Implemented in Source may remain independently supportable.

### 2.8 Production Operation

**Meaning and authority.** The actual supported production path is deployed and
operating in the expressly stated scope.

**Minimum evidence.** Current production deployment identity and observations
must show that the supported artifact and path are operating in the claimed
production environment. The evidence must cover the behavior the wording
asserts; architecture, source, or qualification evidence cannot substitute for
production observation.

**Does not imply.** “Production architecture” names a decision, and a
“production-capable target” describes design intent. Neither proves a production
deployment. A local production-like configuration, CI run, disposable fixture,
development or staging deployment, one infrastructure qualification, or a merge
to `main` does not prove Production Operation.

Unqualified **production-ready** is prohibited. The phrase has no single bounded
meaning across security, reliability, support, operations, deployment, legal,
and product scope. Authors MUST instead state the evidenced fact, such as a
specific production operation or qualification, and its scope. A separately
owned, explicit readiness contract could support a correspondingly bounded
phrase in the future; no weaker claim may do so.

**Change and downgrade.** A stopped, replaced, unsupported, contradictory, or
unobservable production path loses the current claim. If current production
deployment evidence remains valid, Production Deployment remains independently
supportable even though Production Operation ceases. Deployed to Development /
Test, Implemented in Source, or Historical Production Operation may also remain
supportable in their own scopes.

### 2.9 Accepted Architecture

**Meaning and authority.** The authoritative ADR status says an architecture
decision is currently Accepted, interpreted together with current refinement
and supersession relationships. The ADR index and individual ADRs remain the
registry; this document does not snapshot or replace them.

**Minimum evidence.** Current ADR authority supports the exact architectural
scope. Public wording MAY call it “the accepted architecture” or “the accepted
target”. Proposed material MUST be described as proposed or non-binding;
Superseded and Partially Superseded material MUST expose the current status and
the surviving scope; historical context MUST be identified as such.

**Does not imply.** Acceptance proves a binding decision, not source
implementation, migration completion, deployment, external verification,
production readiness, or Production Operation.

**Change and downgrade.** Public wording follows current ADR authority when a
decision is refined, partially superseded, superseded, or otherwise changes
status. An old implementation can temporarily remain in source after its ADR is
superseded; the architecture claim changes even though the source claim has not
yet changed.

### 2.10 Qualification / PoC / Exploration

**Meaning and authority.** A candidate, prototype, proof of concept,
qualification exercise, provider test, architecture experiment, or exploratory
product/domain idea is being evaluated or has bounded exploratory evidence.

**Minimum evidence.** The owning evaluation source identifies the hypothesis or
candidate, scope, and result. Public wording MAY say “under qualification”,
“evaluated as a proof of concept”, or “being explored”. A successful result
proves only that result within its exercised scope.

**Does not imply.** A preferred candidate or successful PoC is not thereby
Accepted Architecture, a selected production path, Implemented in Source as a
supported capability, or a guaranteed roadmap commitment.

**Change and downgrade.** If qualification ends without adoption, report the
bounded result as Historical where useful. Adoption requires an explicit
transition in the later owning product, architecture, planning, or
implementation authority; public prose cannot perform that transition.

### 2.11 Historical / Superseded

**Meaning and authority.** Evidence, a decision, implementation, deployment, or
work result remains valid history but no longer establishes the corresponding
current state.

**Minimum evidence.** Preserved immutable or attributable evidence establishes
what was true, while current authority establishes that the subject or scope is
retired, superseded, replaced, or no longer supported. Public wording SHOULD use
past tense and identify the historical scope when confusion with current support
is plausible.

**Does not imply.** A historical success does not prove current support.
Superseded ADRs do not bind current architecture except for any explicitly
surviving scope. Completed historical migration or old qualification does not
establish the current runtime, provider, or version.

**Change and downgrade.** Historical evidence is preserved rather than erased.
If a current claim loses currentness but the old fact remains valid, convert it
to this class instead of silently retaining present tense.

## 3. Currentness, downgrade, and conflict

### 3.1 Semantic currentness

There is no universal evidence-expiry period. Evidence is current while it still
supports the same current subject and scope. It becomes stale for a claim when,
for example:

- the authoritative branch materially changes;
- the implementation is removed, replaced, or no longer supported;
- an ADR is refined or superseded;
- a supported runtime, provider, protocol, or version changes;
- environment topology or the exercised seam changes;
- the evidence source becomes inaccessible;
- newer evidence contradicts it; or
- the claimed path is no longer the path that the evidence exercised.

Old evidence may remain historically valid after it stops being current.

### 3.2 Downgrade rule

> When evidence required for a current claim is missing, stale, superseded,
> inaccessible, contradictory, or narrower than the prose, downgrade, qualify,
> or omit the prose to the strongest claim that the remaining evidence actually
> supports in the relevant claim class and scope.

There is no universal fallback. Operationally / Externally Verified may become
Implemented in Source; a development deployment may disappear while the source
claim remains; Production Operation may cease while a still-current Production
Deployment remains; Accepted Architecture may become Superseded while its old
implementation temporarily remains; Active Implementation may become Planned /
Tracked Work; and a current verified path may become Historical.

### 3.3 Contradictory evidence

When authoritative sources materially conflict, authors MUST NOT select the more
flattering statement. Apply the precedence and ownership already defined by the
canonical contracts. If no current authority resolves the conflict, use the
weaker or explicitly qualified statement, or omit it until resolved. Record
genuine governance or documentation drift through its owning process rather
than normalizing the conflict in public prose. This contract creates no new
source-precedence hierarchy.

### 3.4 No claim by absence

These rules govern positive factual claims. Missing evidence does not authorize
an inverse claim. In particular, no production evidence does not prove a system
unsafe; no active issue does not prove rejection of an idea; no public roadmap
date does not prove an absence of internal prioritisation; and no current
external verification does not prove an implementation broken.

## 4. Work-graph qualifiers in public prose

The work-graph contract exclusively owns `READY`, `BLOCKED`, `ACTIVE`, `NEXT`,
and `DONE`, including their derivation and evidence classes. Public authors use
these consequences without copying their definitions:

- **tracked or open** means tracked or open, not active;
- **assigned** means ownership, not execution;
- **`READY`** means executable under the canonical graph, not implemented;
- **`BLOCKED`** is a work condition, not product maturity;
- **`ACTIVE`** is available only when the canonical work-graph definition is
  satisfied;
- **`NEXT`** is execution selection, not a public delivery promise; and
- **`DONE`** records native completed closure of the delivery node but does not
  broaden the node's contract or evidence into deployment, verification, or
  production claims.

Board state, issue labels, assignees, roadmap location, and sibling order do not
override these semantics.

## 5. Public roadmap and product wording

A curated public roadmap may translate internal evidence into product-quality
prose without publishing the raw graph. Each statement still needs the
appropriate class:

- **foundation work** may be Accepted Architecture, Planned / Tracked Work,
  Active Implementation, Implemented in Source, or a combination, but the
  wording MUST say which fact matters;
- **implemented capability** requires Implemented in Source evidence and must
  preserve its delivered scope;
- **project active-development / pre-1.0 context**, including the stable
  statement that SecPal is under active development and remains pre-1.0, is
  governed by the product-positioning contract. It describes overall project
  maturity and continuing evolution and does not require a continuously present
  Work-Graph `ACTIVE` leaf. It does not imply that every product domain or any
  named feature or issue is active, continuous commit activity, proximity to a
  release, or production readiness;
- **active implementation of a named capability or delivery** requires current
  Active Implementation evidence. For work governed by the SecPal work graph,
  canonical `ACTIVE` remains exclusively defined there;
- **product direction** requires Product Direction authority and is not a
  feature promise; and
- **exploration** remains Qualification / PoC / Exploration unless its owning
  authority explicitly changes.

Display order, “now / next / later” grouping, and narrative flow MUST NOT be
treated as fixed dates, guaranteed sequence, guaranteed delivery, or evidence
that later items are blocked by earlier ones. Public authors may omit volatile
internal mechanics, but omission cannot turn a direction or preference into a
commitment.

## 6. Illustrative SecPal applications

These examples were initially inspected on 2026-08-29 to demonstrate use of the
vocabulary. The Accepted-ADR-range example was refreshed on 2026-09-06 to include
ADR-024. They are illustrative snapshots, not new authority for the underlying
technical state. Authors MUST consult the named current owners before repeating
any factual state.

### Accepted production architecture and unfinished delivery

[ADR-017 through ADR-024](adr/README.md) are currently indexed as Accepted and
therefore support appropriately scoped Accepted Architecture wording.
[Epic #695](https://github.com/SecPal/.github/issues/695) and its owning
implementation work separately govern migration and delivery. ADR acceptance
alone cannot make that architecture Implemented in Source, deployed, verified,
or in Production Operation. Each of those claims needs its own current evidence.
The completed [ADR reconciliation #717](https://github.com/SecPal/.github/issues/717)
is delivery evidence for the ADR corpus, not runtime implementation evidence;
the same boundary applies to accepted [ADR-014](adr/20260720-tenant-identity-access-model-adr014.md).

### Historical and scoped deployment evidence

[SecPal/deployment#127](https://github.com/SecPal/deployment/issues/127) owns
reconciliation of cross-cutting deployment documentation with the supported
path. The deployment repository also preserves successful earlier integration
and image-consumption evidence while expressly scoping it to disposable or
non-production paths. Such evidence can support a scoped historical or
Operationally / Externally Verified statement; it cannot support current
production deployment or Production Operation after the supported path changes.

### Incomplete OpenAPI coverage

The current `SecPal/contracts` OpenAPI source and its verified-operation guard
support claims about the represented and checked operations. Its README also
identifies backend routes that are not represented. The existence of an OpenAPI
source, a green lint run, or validation of named routes therefore cannot become
“all API contracts are covered”. [SecPal/api#1453](https://github.com/SecPal/api/issues/1453)
likewise illustrates that current API-facing documentation has an owning
reconciliation contract; an open owner does not itself prove active execution or
completion.

### Curated roadmap order on `secpal.app`

[SecPal/secpal.app#61](https://github.com/SecPal/secpal.app/issues/61) records
that the roadmap is curated public copy rather than a direct rendering of issue
state. Its current “Now / Next / Later” presentation can be translated only
through current evidence: a named “Now” item described as actively in
development needs Active Implementation evidence, “Next” may express Planned /
Tracked Work but not guaranteed order, and “Later” may be Product Direction or
Qualification / PoC / Exploration. Display order cannot establish a guaranteed
sequence such as scheduling, then OWKS, then contracts.

## Scope boundary

This contract defines semantics for later public documentation work. It does not
rewrite a repository README, organization profile, website, roadmap, deployment
or API documentation, or sibling repository. It changes no ADR status,
work-graph state, evidence architecture, implementation, deployment, or runtime
behavior, and it creates no universal compliance or production-readiness
certification system.
