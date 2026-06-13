<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-0006: App UI Stack

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

SecPal and GuardGuide application surfaces need consistent component behavior, accessibility patterns, iconography, styling vocabulary, and dark-mode support. The organization needs a standard stack while keeping shared standards separate from product implementation details.

## Decision

The approved application UI stack is shadcn/ui for component composition, Radix UI for accessible primitives, Tailwind CSS for utility styling and token-backed visual implementation, and Lucide icons for standard interface iconography.

Product repositories own installation, file layout, build configuration, token values, routing, component APIs, runtime assets, and product-specific code wiring. Shared standards define the approved stack and expected behavior only.

## Rationale

This stack provides accessible primitives, practical composition patterns, token-friendly styling, and consistent iconography while still letting each product own its implementation.

## Consequences

### Positive

- Products can share interaction and accessibility expectations without depending on shared runtime implementation packages.
- Standard controls, focus behavior, dark-mode tokens, and icons become easier to recognize across surfaces.
- Product repositories retain control over framework integration and release timing.

### Negative

- Product teams must resist adding parallel UI libraries for ordinary controls.
- Specialized workflows still need local documentation when they require custom components.

## Alternatives Considered

1. **Publish shared implementation packages**
   - Pro: strongest implementation reuse
   - Contra: adds release coupling and is outside the scope of these shared standards
2. **Allow any UI library per product**
   - Pro: maximum local choice
   - Contra: fragments accessibility behavior, icons, styling, and maintenance expectations

## Related

- [Components](../design/components.md)
- [Accessibility](../design/accessibility.md)
- [Dark Mode](../design/dark-mode.md)
