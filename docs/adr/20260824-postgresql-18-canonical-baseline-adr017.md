<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-017: PostgreSQL 18 Canonical Database Baseline

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

The 0.x production baseline must not retain an unnecessary database-major or SQL-engine compatibility matrix.

## Binding decision

PostgreSQL 18 is the sole active major for development, CI/integration, and new production reference deployments. Production PostgreSQL is host-native systemd/SELinux infrastructure; disposable PG18 containers are permitted only for bounded development/test use. PostgreSQL 16/17 are historical, migration, or negative-test evidence only. Future major upgrades start from PG18 and require separate qualification.

SecPal deliberately uses PostgreSQL-specific semantics where appropriate; it makes no multiple-SQL-engine promise. PostgreSQL initially owns relational data, DB-backed sessions, durable queues, and shared cache. Valkey is not part of the current reference architecture and may return only through a new explicit, benchmark-backed architecture decision.

## Invariants and consequences

No unreleased future major is supported or pre-accepted. This reduces active operational surfaces while making later upgrades an explicit qualification activity.

## Alternatives and relationships

Retaining PG16/17 or generic SQL compatibility was rejected as obsolete 0.x compatibility. See [#704](https://github.com/SecPal/.github/issues/704), [#695](https://github.com/SecPal/.github/issues/695), ADR-020, and ADR-022.
