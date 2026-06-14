<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# BRAND-0006: App UI Stack Ownership

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

SecPal and GuardGuide application surfaces need consistent component behavior, accessibility patterns, iconography expectations, styling vocabulary, and dark-mode support. Contributors also need clear boundaries between organization-wide design guidance and repository-local runtime implementation choices.

## Decision

This repository does not define one required runtime UI stack for every SecPal surface.

Product repositories own their framework, component library, styling system, icon set, installation, file layout, build configuration, token values, routing, component APIs, runtime assets, and product-specific code wiring.

Shared standards in `.github` define cross-product expectations such as accessibility, predictable component states, navigation behavior, and documentation boundaries without turning product-local stack choices into organization-wide mandates.

## Rationale

Keeping stack selection in the owning repository avoids false organization-wide mandates while still allowing shared design guidance to describe the behaviors every surface should preserve.

## Consequences

### Positive

- Products can share interaction and accessibility expectations without depending on a central runtime stack decision.
- Product repositories retain control over framework integration, release timing, and platform-specific implementation choices.
- Shared standards can stay stable even when different products use different UI technologies.

### Negative

- Product repositories must document their chosen stack clearly enough that contributors can follow local conventions.
- Cross-product visual consistency depends on behavior and review discipline instead of a single enforced library choice.

## Alternatives Considered

1. **Approve one shared runtime stack for every product**
   - Pro: strongest implementation uniformity
   - Contra: conflicts with repository-local ownership and existing per-product instruction paths
2. **Provide no shared component guidance at all**
   - Pro: maximum local choice
   - Contra: weakens cross-product expectations for accessibility and interaction behavior

## Related

- [Components](../design/components.md)
- [Accessibility](../design/accessibility.md)
- [Dark Mode](../design/dark-mode.md)
