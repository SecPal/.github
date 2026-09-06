<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-022: Deployment Topology Evolution and High Availability

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that the original ADR pull request first made those
decisions. The 2026-09-06 refinement under
[#843](https://github.com/SecPal/.github/issues/843) reconciles local HA,
Managed capability profiles, and controlled cross-provider continuity with the
September 2026 production architecture. It retains the original text below as
historical evidence and replaces only the conflicting current baseline; it is
not a successor ADR or an implementation plan.

## Context

Self-hosting, host replacement, and permanent HA have materially different guarantees.

## Original August 2026 binding decision (historical evidence)

This section preserves the original accepted baseline. Where it differs from
the current binding refinement below, the refinement controls current
architecture.

The topology vocabulary is `single`, temporary `replacement`, and permanent `ha`. `single` is the normal supported self-host topology and requires neither Patroni/DCS nor a database router. Same-major PG18 replacement uses physical streaming replication; floating IP/provider routing may be used without requiring an application load balancer, and application architecture does not change. Future major upgrade starts from PG18 and is separately qualified; logical replication or another reviewed method may be selected later.

HA is distinct from backup. Patroni is the preferred PostgreSQL HA coordinator subject to qualification, with a real quorum DCS (etcd is a candidate), no two-node quorum fiction, exactly one writable primary/fencing semantics, a stable private/node-local write endpoint, and shared durable object storage for authoritative private files. Barman remains an independent recovery chain. RPO/RTO and synchronous-replication choices must be measured and explicit.

## Current binding refinement

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
