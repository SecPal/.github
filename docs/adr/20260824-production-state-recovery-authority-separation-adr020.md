<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-020: Production State, Recovery, and Cryptographic Authority Separation

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

Durable state, recovery proof, and cryptographic custody must remain explicit and separable.

## Binding decision

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

## Consequences

Recovery is a provable set of compatible state and authority generations, not a
successful backup job. Separate custody narrows compromise impact and makes a
missing authority an explicit recovery failure rather than silent data loss.

## Relationships

See [#695](https://github.com/SecPal/.github/issues/695), ADR-015, ADR-017, and ADR-022.
