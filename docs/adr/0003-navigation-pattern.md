<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-0003: Navigation Pattern

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

SecPal and GuardGuide application surfaces need a consistent shell model for product identity, global destinations, local context, and dense operational work areas. The shared design standard should guide navigation decisions without prescribing route trees, breakpoints, or component APIs for product repositories.

## Decision

Top navigation is the default application shell for SecPal and GuardGuide. The standard desktop pattern includes a persistent topbar, optional breadcrumb or context bar, full-width work area, and local module tabs where a route has peer views. Mobile keeps the topbar as the shell anchor and moves secondary navigation into sheets.

A permanent left sidebar is not the shared default. Product repositories may document focused exceptions for specialist surfaces with a clear workflow need.

## Rationale

Top navigation preserves product identity and global actions while leaving horizontal space for dashboards, tables, forms, audit trails, and other operational views.

## Consequences

### Positive

- Application shells have a consistent starting point across products.
- Dense work areas are not constrained by a default permanent sidebar.
- Mobile navigation can reuse sheet patterns from the approved component stack.

### Negative

- Products with many persistent peer sections may need documented exceptions.
- Existing sidebar-first surfaces need deliberate migration or local exception records.

## Alternatives Considered

1. **Permanent left sidebar as the default**
   - Pro: familiar for administration-heavy tools
   - Contra: consumes horizontal space and makes the shared shell less suitable for dense operational content
2. **Repository-specific shell decisions only**
   - Pro: maximum local autonomy
   - Contra: creates inconsistent navigation behavior between SecPal products

## Related

- [Layout](../design/layout.md)
- [Navigation](../design/navigation.md)
- [Accessibility](../design/accessibility.md)
