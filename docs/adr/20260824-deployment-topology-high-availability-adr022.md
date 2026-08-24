<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-022: Deployment Topology Evolution and High Availability

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

Self-hosting, host replacement, and permanent HA have materially different guarantees.

## Binding decision

The topology vocabulary is `single`, temporary `replacement`, and permanent `ha`. `single` is the normal supported self-host topology and requires neither Patroni/DCS nor a database router. Same-major PG18 replacement uses physical streaming replication; floating IP/provider routing may be used without requiring an application load balancer, and application architecture does not change. Future major upgrade starts from PG18 and is separately qualified; logical replication or another reviewed method may be selected later.

HA is distinct from backup. Patroni is the preferred PostgreSQL HA coordinator subject to qualification, with a real quorum DCS (etcd is a candidate), no two-node quorum fiction, exactly one writable primary/fencing semantics, a stable private/node-local write endpoint, and shared durable object storage for authoritative private files. Barman remains an independent recovery chain. RPO/RTO and synchronous-replication choices must be measured and explicit.

## Non-goals and relationships

HA is not mandatory for normal single-node deployments, and no unreleased PostgreSQL major is pre-accepted. See [#695](https://github.com/SecPal/.github/issues/695), ADR-017, ADR-019, and ADR-020.
