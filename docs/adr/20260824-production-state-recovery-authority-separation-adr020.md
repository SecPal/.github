<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-020: Production State, Recovery, and Cryptographic Authority Separation

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that the original ADR pull request first made those
decisions. The 2026-09-06 refinement under
[#843](https://github.com/SecPal/.github/issues/843) reconciles recovery and
Managed storage authority with the September 2026 production architecture. It
retains the original text below as historical evidence and replaces only the
conflicting current baseline; it is not a successor ADR or an implementation
plan.

## Context

Durable state, recovery proof, and cryptographic custody must remain explicit and separable.

## Original August 2026 binding decision (historical evidence)

This section preserves the original accepted baseline. Where it differs from
the current binding refinement below, the refinement controls current
architecture.

PostgreSQL is authoritative for relational/session/queue/cache state; private application files are distinct authoritative state. Container writable layers are never authoritative. Single topology uses durable host storage outside containers; HA uses provider-neutral shared durable object storage through the application abstraction.

Backup is not HA and replication is not backup. PostgreSQL backup/WAL uses
off-cluster, asynchronous Barman with one canonical external continuous WAL
stream; it is never a synchronous-commit participant. Loss of WAL continuity
invalidates the recovery chain until a new valid base anchor exists. Private
files in single topology use Borg with encrypted compatible remote storage;
Borg never backs up live PGDATA. Permanent-HA shared object-storage durability
or replication is not backup and requires an independent recovery-copy
contract. A topology-independent **Recovery Set** couples database restore
identity, private-file/object generation, crypto authority
generations/fingerprints, and schema/app/deployment/recovery-format provenance.
Correctness requires an isolated fresh-environment restore drill. Missing
recovery-critical authority fails; no replacement is auto-generated.

The engineering objectives are PostgreSQL DR RPO <= 2 minutes, private
file/object RPO <= 15 minutes, valid Recovery Set <= 15 minutes, and standard
single-node service recovery RTO <= 2 hours. They are engineering objectives,
not customer SLA promises.

## Current binding refinement

PostgreSQL state, authoritative Private Objects, live storage, replication,
backup, retention, and RecoverySet are distinct truths. Container writable
layers are never authoritative. Managed authoritative Private Objects are
off-host in `MANAGED_SINGLE`, `MANAGED_HA`, and `MANAGED_CONTINUITY` through one
provider-neutral ObjectStorageContract. Object Storage durability or
replication is not Object Backup; an independent topology-neutral Object Backup
contract protects the canonical stored encrypted bytes. The old Managed
`single = local private files + Borg` baseline is no longer current.

Self-hosted deployments retain implementation flexibility. A self-hosted
single-node deployment may use a durable local object adapter and Borg or an
equivalent independent remote recovery copy only when it preserves the same
application/object semantics, keeps authoritative data outside container
writable layers, and satisfies the independent recovery contract. A local path
or Borg repository is not a Managed application-storage authority and must not
become a product-level storage assumption.

Barman is the canonical PostgreSQL 18 base-backup and continuous-WAL recovery
layer. Managed deployments may use a shared remote, reproducibly replaceable
Barman service while retaining deployment-specific identities, namespaces,
credentials, and recovery state. Barman remains asynchronous and outside normal
PostgreSQL synchronous commit and the application request path. These are
separate operational truths:

- Barman Service Availability;
- PostgreSQL Availability;
- Backup Data Durability; and
- Backup Continuity, including an unbroken usable base-backup/WAL chain.

One truth must not be inferred from another. In particular, Barman process
recovery does not prove backup continuity, and PostgreSQL availability does not
prove backup health. Loss of required WAL continuity invalidates the recovery
chain until a new safe base anchor exists.

RecoverySet is the canonical cross-state recovery authority. Each RecoverySet
resolves to exactly one PostgreSQL restore point and WAL LSN, one verified
Private Object recovery boundary and target, every required cryptographic
authority generation or fingerprint, and a portable manifest binding those
facts to their verification evidence and relevant schema, application,
deployment, and recovery-format provenance. A database-only or Object-only
backup is not a RecoverySet.

`VERIFIED` is evaluated for an explicitly addressed failure class. A RecoverySet
is `VERIFIED` for that class only when its required database/WAL, Object,
cryptographic-authority, and manifest state is recoverable outside the failure
domain being addressed. Guaranteed RPO for a failure class derives from the
newest matching `VERIFIED` RecoverySet that survives that class at failure time.
Database replication lag, Object replication lag, backup freshness, and
RecoverySet age remain distinct supporting operational evidence; none alone is
the guaranteed cross-state RPO authority.

RPO and RTO values are engineering objectives to be selected, measured, and
qualified for an explicit technical profile and failure class. Architecture
acceptance does not turn them into customer SLA or production-proof claims.
Fresh isolated recovery drills provide recoverability evidence; deployment and
production qualification remain owned by their existing implementation and
operations contracts.

## Authority invariants

- **Deployment Root KEK / root wrapping authority** is off-database recovery
  authority for the tenant envelope hierarchy.
- **Tenant-scoped wrapped key material** is PostgreSQL-held wrapped tenant
  cryptographic material, never a plaintext backup export.
- **ADR-015 Global Identity Root / KEK** is a separate root authority and never
  the Deployment Root KEK.
- **`APP_KEY`** is separate and recovery-critical only while persistent
  Laravel/framework encrypted state still references it.
- **PostgreSQL credentials** for runtime, migration/DDL, backup, and replication
  are least-authority distinct consumers.
- **PostgreSQL transport PKI** separates database server certificate/key and
  trust CA from the CA signing/root private key. That private key is a separate
  recovery/security authority outside Git and product containers, and not solely
  inside PGDATA or database state.
- Backup encryption/repository credentials and public TLS/ACME private keys are
  separate authorities.

Missing required authority fails; existing encrypted or identity-bound state
never triggers auto-generation of a replacement. KEK/root rotation rewraps,
data-key rotation re-encrypts, blind-index-key rotation rebuilds indexes, and
DB PKI rotation uses validated overlap/trust transition.

RecoverySet manifests identify required generations but contain no secret key
material. Missing historical cryptographic authority required by a supported
RecoverySet is recovery failure; recovery must not invent replacement keys or
lower enrollment, identity, or activation boundaries.

## Consequences

Recovery is a provable set of compatible state and authority generations, not a
successful backup job. Separate custody narrows compromise impact and makes a
missing authority an explicit recovery failure rather than silent data loss.

## Relationships

See [#695](https://github.com/SecPal/.github/issues/695),
[#800](https://github.com/SecPal/.github/issues/800),
[#843](https://github.com/SecPal/.github/issues/843), ADR-015, ADR-017, ADR-022,
and ADR-023. Existing public implementation ownership remains in
`SecPal/deployment`; private Managed composition remains in
`SecPal/operations`.
