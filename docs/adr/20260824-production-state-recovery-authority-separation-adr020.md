<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-020: Production State, Recovery, and Cryptographic Authority Separation

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

Durable state, recovery proof, and cryptographic custody must remain explicit and separable.

## Binding decision

PostgreSQL is authoritative for relational/session/queue/cache state; private application files are distinct authoritative state. Container writable layers are never authoritative. Single topology uses durable host storage outside containers; HA uses provider-neutral shared durable object storage through the application abstraction.

Backup is not HA and replication is not backup. PostgreSQL backup/WAL uses off-cluster asynchronous Barman; private files in single topology use Borg with encrypted compatible remote storage; Borg never backs up live PGDATA. A topology-independent **Recovery Set** couples database restore identity, private-file/object generation, crypto authority generations/fingerprints, and schema/app/deployment/recovery-format provenance. Correctness requires an isolated fresh-environment restore drill. Missing recovery-critical authority fails; no replacement is auto-generated. Rebaseline RPO/RTO figures are engineering objectives, not customer SLAs.

## Authority invariants

Tenant/Deployment Root KEK, ADR-015 Global Identity Root/KEK, tenant wrapped material, recovery-critical `APP_KEY`, PostgreSQL runtime/migration/backup/replication credentials, PostgreSQL transport CA/signing/server identity, backup encryption/repository credentials, and TLS/ACME private keys remain distinct authorities. Rotation means: root/KEK rewraps, data-key re-encrypts, index-key rebuilds indexes, and DB PKI uses validated trust overlap.

## Relationships

See [#695](https://github.com/SecPal/.github/issues/695), ADR-015, ADR-017, and ADR-022.
