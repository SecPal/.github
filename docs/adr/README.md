<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for SecPal.

## What are ADRs?

ADRs document significant architectural decisions made during the development of SecPal. They provide context about why certain decisions were made and what alternatives were considered.

## Format

Each ADR follows this structure:

```markdown
# ADR-XXX: Title

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-YYY

**Date:** YYYY-MM-DD

**Deciders:** @kevalyq (+ others as project grows)

## Context

What is the issue we're addressing?

## Decision

What decision did we make?

## Consequences

What are the positive and negative outcomes?

### Positive

- ...

### Negative

- ...

## Alternatives Considered

What other options did we evaluate?

1. **Option 1:** Description
   - Pro: ...
   - Contra: ...

2. **Option 2:** Description
   - Pro: ...
   - Contra: ...

## Related

- Issue #123
- ADR-002
- [External link](https://example.com)
```

## Naming Convention

Files are named: `YYYYMMDD-short-descriptive-title.md`

Examples:

- `20251027-event-sourcing-for-guard-book.md`
- `20251028-postgresql-temporal-tables.md`
- `20251030-digital-signature-strategy.md`

## Index

<!-- New ADRs are added here in reverse chronological order -->

### Accepted

- [ADR-011: Simplify Management Level from Model to Integer Field](20251227-simplify-management-level-to-integer-field-adr011.md) - 2025-12-27
- [ADR-010: Activity Logging & Audit Trail Strategy](20251221-activity-logging-audit-trail-strategy.md) - 2025-12-24
- [ADR-008: User-Based Tenant Resolution for Multi-Tenant Architecture](20251219-user-based-tenant-resolution.md) - 2025-12-19
- [ADR-005: RBAC Design Decisions](20251111-rbac-design-decisions.md) - 2025-11-11
- [ADR-004: RBAC System with Spatie Laravel-Permission and Temporal Extensions](20251108-rbac-spatie-temporal-extension.md) - 2025-11-08

### Proposed

- [ADR-009: Permission Inheritance Blocking & Leadership-Based Access Control](20251221-inheritance-blocking-and-leadership-access-control.md) - 2025-12-21 (Partially superseded by ADR-011)
- [ADR-007: Flexible Organizational Structure & Multi-Level Hierarchies](20251126-organizational-structure-hierarchy.md) - 2025-11-26
- [ADR-001: Event Sourcing for Guard Book Entries](20251027-event-sourcing-for-guard-book.md) - 2025-10-27
- [ADR-002: OpenTimestamp for Audit Trail](20251027-opentimestamp-for-audit-trail.md) - 2025-10-27
- [ADR-003: Offline-First Architecture](20251027-offline-first-architecture.md) - 2025-10-27

### Superseded

_None yet_

## When to Write an ADR

Write an ADR when making decisions about:

- **Architecture:** Event sourcing, CQRS, microservices vs. monolith
- **Technology:** Database choice, framework selection, third-party services
- **Security:** Authentication mechanisms, encryption strategies
- **Legal:** Licensing, CLA requirements, data retention
- **Process:** CI/CD strategy, branching model, release process

## When NOT to Write an ADR

Don't write ADRs for:

- Simple bug fixes
- Code style preferences (use linters/formatters instead)
- Routine dependency updates
- Minor refactorings without architectural impact

## Resources

- [ADR GitHub Organization](https://adr.github.io/)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [Sustainable Architectural Design Decisions](https://www.infoq.com/articles/sustainable-architectural-design-decisions/)
