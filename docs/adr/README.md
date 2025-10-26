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

### Proposed

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
