<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-0002: Typography

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

SecPal and GuardGuide need readable, consistent typography across application UI, public copy, generated documents, and contributor-facing materials. The shared standard must define typography direction without owning product-specific CSS files, font packaging, or exact implementation wiring.

## Decision

Inter is the primary and only default typeface for SecPal and GuardGuide surfaces. Shared standards allow weights `400`, `500`, `600`, and `700`, avoid a default display font, avoid global OpenType character variants such as `cv11`, and keep typography scales restrained for operational interfaces.

Product repositories own font hosting, fallback stacks, CSS implementation, platform-specific syntax, and documented exceptions.

## Rationale

A single default typeface keeps brand expression consistent while reducing maintenance overhead and avoiding decorative typography that weakens dense operational workflows.

## Consequences

### Positive

- UI, documentation, and generated materials share a predictable visual voice.
- Product teams can implement the standard in their own framework without central runtime assets.
- Avoiding global character variants keeps text rendering stable across platforms.

### Negative

- Product repositories that already use other default fonts need migration work.
- Specialized surfaces must document exceptions instead of silently introducing alternate type systems.

## Alternatives Considered

1. **Add a separate display font**
   - Pro: more expressive marketing hierarchy
   - Contra: increases asset and rendering complexity without improving product usability
2. **Let each product choose its own default font**
   - Pro: maximum local flexibility
   - Contra: fragments the shared brand and generated document appearance

## Related

- [Typography](../design/typography.md)
