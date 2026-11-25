<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-020: Production State, Recovery, and Cryptographic Authority Separation

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Refinement:** [#843](https://github.com/SecPal/.github/issues/843) defines the
current Managed storage and failure-class-specific recovery boundaries.

## Binding decision

PostgreSQL state, authoritative Private Objects, live storage, replication,
backup, retention, and RecoverySet are distinct truths. Container writable
layers are never authoritative. Managed authoritative Private Objects are
off-host in `MANAGED_SINGLE`, `MANAGED_HA`, and `MANAGED_CONTINUITY` through one
provider-neutral ObjectStorageContract. Object Storage durability or
replication is not Object Backup; an independent topology-neutral Object Backup
contract protects the canonical stored encrypted bytes.

Self-hosted deployments retain implementation flexibility. A self-hosted
single-node deployment may use a durable local object adapter and Borg or an
equivalent independent remote recovery copy only when it preserves the same
application/object semantics, keeps authoritative data outside container
writable layers, and satisfies the independent recovery contract. A local path
or Borg repository is not a Managed application-storage authority and must not
become a product-level storage assumption. Borg does not protect live PGDATA.

Barman is the canonical PostgreSQL 18 base-backup and continuous-WAL recovery
layer. Each deployment keeps one authoritative external continuous WAL stream.
Managed deployments may use a shared remote, reproducibly replaceable Barman service while retaining deployment-specific identities, namespaces,
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
