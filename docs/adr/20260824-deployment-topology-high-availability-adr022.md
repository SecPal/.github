<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-022: Deployment Topology Evolution and High Availability

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Refinement:** [#843](https://github.com/SecPal/.github/issues/843) defines
local HA, Managed capability profiles and controlled cross-provider continuity.

## Binding decision

The self-hosted deployment topology vocabulary remains `single`, temporary
`replacement`, and permanent `ha`. Normal self-hosted `single` requires neither
Patroni/DCS nor a database router. The Managed technical capability profiles
are:

- `MANAGED_SINGLE`: recoverable operation without automatic customer-host
  failover;
- `MANAGED_HA`: automatic continuity for one qualified local compute-host
  failure; and
- `MANAGED_CONTINUITY`: local HA plus controlled warm independent-provider
  disaster recovery.

These profiles name technical capability and bound the failure classes each
profile is intended to address. They are not customer SLA names, availability
percentages, or claims of qualification or production proof. An implementation
must not claim a profile's guarantee until its owning qualification and
production evidence establish that failure-class contract.

### Host replacement and major upgrades

Same-major PostgreSQL 18 replacement uses physical streaming replication.
Provider routing or a floating IP may switch the application endpoint without
an application load balancer or a change in application architecture. A future
major upgrade starts from PostgreSQL 18 and requires separate qualification.
Logical replication or another reviewed method can be selected for that upgrade.

### Local PostgreSQL HA

PostgreSQL 18 local HA uses Patroni as the PostgreSQL HA authority with a real
quorum DCS. Deployment-specific etcd v3 is the reference DCS: each deployment
has an independent consensus domain, and no fleet-wide shared Patroni DCS is the
baseline. Patroni owns writer election and PostgreSQL role authority. Exactly
one PostgreSQL writer may exist.

Automatic local promotion requires qualified fencing/watchdog behavior for the
supported Patroni, DCS, operating-system, and failure-domain combination. An old
primary that has lost authority must not continue accepting authoritative
writes; ambiguous quorum or fencing state fails closed rather than inventing a
writer.

`db.secpal.internal` is the stable private PostgreSQL write-service identity for
both `single` and local HA. Routing may discover and forward new connections to
the Patroni-confirmed writer, but routing, reachability, DNS, and HAProxy do not
elect or create writer authority. When no unambiguous Patroni-confirmed writer
exists, the write service is unavailable.

### Application HA

API and frontend instances are active/active. Workers are active/active with
at-least-once delivery, and jobs must be idempotent for that contract. Redundant
schedulers coordinate through PostgreSQL-backed locking. Application HA has no
application primary, requires no sticky sessions, and introduces no
Valkey/Redis or separate leader service solely for HA. PostgreSQL-backed
sessions, queue, cache, and coordination remain consistent with ADR-017.

### Cross-provider continuity

Local automatic HA operates only inside its explicitly qualified local failure
domain. The cross-provider PostgreSQL baseline is asynchronous, and the remote
provider is outside the local Patroni DCS and election domain. Cross-provider
promotion is a controlled operation, not blind automatic WAN election. It
requires fencing of obsolete authority and a safe RecoverySet, PostgreSQL, and
Private Object boundary suitable for the addressed provider-loss failure class
before production routing or writes are enabled.

Local HA success is not provider-loss continuity proof. Barman, Object Backup,
and RecoverySet remain independent recovery authorities under ADR-020; live
replication or a successful local failover cannot substitute for them.

## Consequences

Normal self-hosting remains feasible without HA machinery, while replacement
and permanent HA have explicit, separately measurable contracts. A topology
cannot claim resilience merely from replication or shared storage.

## Non-goals and relationships

HA is not mandatory for normal single-node deployments, and no unreleased
PostgreSQL major is pre-accepted. Kubernetes is not introduced solely to obtain
SecPal HA; adding it later requires a separate explicit architecture decision
and must not become a hidden normal-self-hosting requirement. This ADR changes
no implementation owner: public portable delivery and qualification remain in
`SecPal/deployment`, and private Managed composition remains in
`SecPal/operations`. See [#695](https://github.com/SecPal/.github/issues/695),
[#800](https://github.com/SecPal/.github/issues/800),
[#843](https://github.com/SecPal/.github/issues/843), ADR-017, ADR-019, ADR-020,
and ADR-023.
