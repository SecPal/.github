<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-017: PostgreSQL 18 Canonical Database Baseline

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

The 2026-11-19 Managed refinement under
[#1347](https://github.com/SecPal/.github/issues/1347) changes infrastructure
placement and supply qualification while preserving the PostgreSQL 18 and
authority contracts. Historical host-native qualification does not qualify the
container path.

## Context

The 0.x production baseline must not retain an unnecessary database-major or SQL-engine compatibility matrix.

## Binding decision

PostgreSQL 18 is the sole active major for development, CI/integration, and new
production reference deployments. The Managed FCOS reference uses independently
qualified infrastructure containers under Podman/Quadlet, defaulting to rootless
operation under ADR-018. This replaces the host-native-only and CI-container-only
placement restrictions; it does not turn a disposable fixture into a production
database. PostgreSQL 16/17 are historical, migration, or negative-test evidence
only. Future major upgrades start from PostgreSQL 18 and require separate
qualification.

SecPal deliberately uses PostgreSQL-specific semantics; it makes no multiple-SQL-engine promise. PostgreSQL initially owns relational data, DB-backed sessions, durable queues, and shared cache. The application relies on transactional integrity, transaction-level advisory locks, row locking, JSONB, UUIDs, and relational constraints where those semantics define the operation. Valkey is not part of the current reference architecture and may return only through a new explicit, benchmark-backed architecture decision.

Managed production image supply follows ADR-021: exact digest, publisher/source
provenance, architecture-specific manifest, vulnerability and build evidence,
and native runtime qualification. The earlier qualified Rocky/RHEL Application
Stream remains historical evidence for that native implementation, not the
Managed FCOS supply path. Database qualification includes persistent state
outside container writable layers, explicit ownership and SELinux confinement,
durable flush/fsync behavior, restart/crash recovery, upgrades, and Barman/WAL
and RecoverySet compatibility. A container restart or healthy SQL query alone
does not prove these properties.

Application containers connect by explicit TCP, never
a mounted PostgreSQL Unix socket or `Network=host`. In single topology,
the host-visible database endpoint remains loopback-only; container port
publication must not expand it to public or generic gateway access. Rootless
application access uses the
reviewed narrow pasta host-loopback mapping and a logical hostname such as
`db.secpal.internal`. Generic `host.containers.internal` and broad gateway
exposure are not architecture. Application-to-PostgreSQL transport uses TLS
from the start with `sslmode=verify-full` and SCRAM-SHA-256; channel binding may
become required only after supported-stack qualification. Runtime application,
migration/DDL, backup, and replication authorities are distinct, and the
frontend receives no database credential.

## Invariants and boundaries

No unreleased future major is supported or pre-accepted. The connection seam is
narrow, identity-verified, and does not create a generic host-network escape.

## Consequences

This removes the PG16/17 and Valkey transition matrix and fixes a durable
least-authority database seam. Future upgrades, changed package provenance, or
different connection boundaries require explicit qualification rather than an
ordinary implementation issue.

## Alternatives and relationships

Retaining PG16/17 or generic SQL compatibility was rejected as obsolete 0.x compatibility. See [#704](https://github.com/SecPal/.github/issues/704), [#695](https://github.com/SecPal/.github/issues/695), ADR-020, and ADR-022.
