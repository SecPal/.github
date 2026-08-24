<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-017: PostgreSQL 18 Canonical Database Baseline

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

The 0.x production baseline must not retain an unnecessary database-major or SQL-engine compatibility matrix.

## Binding decision

PostgreSQL 18 is the sole active major for development, CI/integration, and new production reference deployments. Production PostgreSQL is host-native systemd/SELinux infrastructure; disposable PG18 containers are permitted only for bounded development/test use. PostgreSQL 16/17 are historical, migration, or negative-test evidence only. Future major upgrades start from PG18 and require separate qualification.

SecPal deliberately uses PostgreSQL-specific semantics where appropriate; it makes no multiple-SQL-engine promise. PostgreSQL initially owns relational data, DB-backed sessions, durable queues, and shared cache. Valkey is not part of the current reference architecture and may return only through a new explicit, benchmark-backed architecture decision.

Production packages come from the qualified Rocky/RHEL 10.2+ PostgreSQL 18
Application Stream unless a later explicit evidence-backed architecture decision
changes that supply path. Application containers connect by explicit TCP, never
a mounted PostgreSQL Unix socket or `Network=host`. In single topology,
PostgreSQL listens only on loopback; rootless application access uses the
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
