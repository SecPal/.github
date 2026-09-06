<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-024: Managed Operations Control Plane Authority and Trust Boundaries

**Status:** Accepted
**Date:** 2026-09-06
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records Managed Operations Control Plane
architecture adopted during the September 2026 rebaseline. The date is the
durable ADR record date, not a claim that the control plane, its privilege gate,
or production qualification has been implemented.

## Context

ADR-023 defines which portable technical capabilities remain public and which
SecPal Managed composition and policy responsibilities are private. It
deliberately does not define the authority, state, reconciliation, or trust
boundaries of an executable Managed Operations Control Plane.

The September 2026 architecture and native work graph now require that separate
authority. This ADR makes the already-decided control-plane contract durable
without implementing it or moving portable capability out of public
repositories.

## Binding decision

### Responsibility and state authority

The private SecPal Managed Operations Control Plane is responsible for Managed
fleet intent, observation, reconciliation, authorization, bounded operation,
acceptance, and non-secret audit. These remain distinct responsibilities:

```text
Desired State
!=
Observed State
!=
Authorization
!=
Operation
!=
Acceptance
```

Desired State is the authoritative Managed fleet intent. Provider state, host
state, monitoring state, and other external observations are **Observed
Evidence**, not intent. The Control Plane must not silently adopt observed
provider reality as Desired State.

PostgreSQL 18 is the initial durable Fleet-State store under ADR-017. Fleet
State may hold the references, identities, generations, authorizations,
operations, observations, acceptance evidence, and audit records needed by this
contract, but never secret values. No additional database, scheduler, queue,
journal, distributed-coordination system, policy engine, or workflow engine is
accepted merely by this ADR.

### Reconciliation and generations

The canonical reconciliation responsibility is:

```text
Desired
-> Observe
-> Diff
-> Authorize
-> Bounded Mutation
-> Read Back
-> Accept / Reject
-> Audit
```

Every authoritative external mutation must be target-scoped and bounded,
generation-bound where applicable, preconditioned, idempotent, independently
read-back verified, explicitly accepted or rejected against its required
postconditions, and auditable without secret values. Only acceptance establishes
new accepted operational truth.

Desired Generation and Accepted Generation are distinct. Desired Generation
identifies the intended fleet state. Accepted Generation identifies the desired
generation whose required postconditions the reconciler has independently
established. An attempted or apparently successful operation does not advance
Accepted Generation by itself.

The deployment administrative lifecycle remains deliberately narrow:

```text
PREPARING
-> ACTIVE
<-> SUSPENDED
-> DECOMMISSIONING
-> DECOMMISSIONED
```

Update, replacement, resize, failover, recovery, reconciliation, and rollout are
Operations, not additional deployment lifecycle states. Replacing a physical
host at the same target rematerializes the same Desired Generation unless fleet
intent itself changes.

One active reconciliation authority per deployment may coordinate Managed
operations. It is not PostgreSQL writer-election authority, Patroni/DCS
authority, customer-runtime authority, or local-HA authority, and it must not
override qualified local HA.

### Command, authorization, operation, and identity

The control-plane trust boundary is:

```text
Command != Authorization != Operation
```

A command expresses requested intent. Authorization proves bounded authority to
attempt it. An operation is the separately recorded execution attempt. Neither a
command nor authorization proves successful execution or acceptance.

The relevant authorities and credentials are also distinct:

```text
Human Identity
!=
Machine Execution Identity
!=
Provider Credential
!=
Secret Authority
!=
Recovery Authority
```

Browser, portal, API-client, and human sessions never receive general provider
credentials or Secret Authority credentials. Purpose-scoped machine credentials
belong at the execution boundary. Authority to cause secret use, rotation, or a
recovery operation does not grant authority to reveal the secret value. No
technical global-superadmin primitive is accepted.

Authorization has the technical strength classes `ROUTINE`, `CONTROLLED`, and
`CRITICAL`. Narrow, safe routine operations and qualified local self-heal or
local HA may be pre-authorized by explicit bounded policy. This ADR does not
select organization-specific roles, a human hierarchy, RBAC versus ABAC, an
identity provider, MFA equipment, approval UX, or multi-party approval policy.

Critical actions require an explicit scoped, bounded, expiring
`ActionAuthorization`, or an equivalent with the same accepted semantics. A
generic administrator flag or authenticated browser session is insufficient.
Where applicable, the authorization binds the action type, deployment or target,
permitted parameters, Desired Generation, validity and expiry, reason, and
required preconditions. Fresh authoritative observations must be revalidated
immediately before mutation; changed target, generation, expiry, or precondition
state invalidates the authorization.

Higher-authority treatment is required where applicable for cross-provider
promotion, production RecoverySet selection, point-in-time recovery, Total-Loss
Recovery, Secret Authority total recovery, cryptographic-compromise response,
and authority-uncertain destructive cleanup. These actions need not share one
human process or authorization mechanism.

### Observation and mutation authority

ADR-023 and ADR-021 remain authoritative for detector and evidence ownership.
The Control Plane preserves:

```text
Observation != Health != Incident != Authority != Action
```

Monitoring, scanners, alerts, and detectors provide evidence. They do not create
provider, data, secret, or recovery mutation authority, and an alert firing must
not directly cause a destructive mutation. A separately authorized policy may
act on monitoring evidence; any qualified local self-heal remains authority
granted by that policy rather than by monitoring itself.

### Availability and break-glass

Control Plane availability is not a prerequisite for normal operation of an
already-activated customer deployment. An Operations Control Plane outage
degrades management and reconciliation; it does not automatically create a
customer-runtime, local database HA, or local application HA outage. Those
systems continue according to their own deployment and qualification contracts.

Break-glass is bounded, exceptional Recovery Authority whose purpose is to
restore the normal Control Plane authority path. It is not a permanent
super-administrator role, parallel fleet manager, shadow control plane, standing
authorization bypass, or general way to reveal secret values.

### Public and private implementation boundary

ADR-023 remains the authority for the public portable-capability and private
Managed-composition ownership boundary. Public repositories continue to own the
portable provider, provisioning, enrollment, recovery, health, and qualification
contracts needed by independent operators. Provider adapters execute those
portable technical operations; they do not decide Managed fleet intent.

Private `SecPal/operations` owns Managed customer and fleet composition, Desired
State, placement and procurement policy, rollout and wave policy, authorization
policy, Managed reconciliation, and commercial or service operating policy. It
consumes public capabilities rather than creating a second private provider
implementation, and it must not redefine public technical meanings such as
`conformant`, `healthy`, `supported`, `recoverable`, or `safe`.

`Never in Git` remains absolute. Neither public nor private Git may contain
credentials, private keys, secret or recovery authority, customer data, or live
Fleet State. Human operators do not receive direct general provider credentials.

### Architecture acceptance and implementation gate

These states are explicitly different:

```text
ADR Accepted
!=
Operations Privilege Gate Implemented
!=
Control Plane Implemented
!=
Production Qualified
```

`SecPal/operations#10` remains the executable Control Plane coordination owner.
`SecPal/operations#11` remains the prerequisite governance and privilege gate
before `SecPal/operations` may contain or execute privileged production
automation. Accepting this ADR does not implement or satisfy that gate and does
not authorize production mutation.

## Consequences

Managed automation has one durable authority model: intent cannot be inferred
from observed reality, mutation cannot be inferred from a command or alert, and
an execution attempt cannot become accepted truth without independent read-back
and acceptance. Local runtime and HA authority remain isolated from fleet
management availability.

The initial design stays a normal application using PostgreSQL 18 and bounded
reconciler workers. Kubernetes solely for orchestration, Kafka, Temporal,
Consul, ZooKeeper, Redis/Valkey, and fleet-wide etcd are not accepted without a
separate proven invariant and architecture decision.

## Non-goals

This ADR introduces no control-plane code, credentials, provider mutation,
customer data, live Fleet State, portal UX, production automation, runtime
change, database change, HA change, or work-graph mutation. It does not implement
or duplicate `SecPal/operations#10`, `SecPal/operations#11`, or their
descendants.

## Relationships

This ADR records [#844](https://github.com/SecPal/.github/issues/844) and the
Managed Control Plane direction coordinated by
[#695](https://github.com/SecPal/.github/issues/695) and reconciled into the
native graph by completed
[#800](https://github.com/SecPal/.github/issues/800). ADR-023 owns the
public/private capability boundary; this ADR consumes that boundary and owns
Managed Control Plane authority, trust, and reconciliation semantics. ADR-017
owns the PostgreSQL 18 baseline, ADR-020 owns recovery and cryptographic
authority separation, ADR-021 owns scanner and supply-chain evidence boundaries,
and ADR-022 owns Managed topology, HA, and continuity profiles.

Executable coordination remains with
[`SecPal/operations#10`](https://github.com/SecPal/operations/issues/10), and its
prerequisite governance and privilege gate remains with
[`SecPal/operations#11`](https://github.com/SecPal/operations/issues/11).
