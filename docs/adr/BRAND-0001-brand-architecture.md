<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# BRAND-0001: Brand Architecture

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

SecPal needs shared brand rules that work across the organization without turning this repository into a product implementation repository. Contributors also need to know when to use `SecPal`, when to use `GuardGuide by SecPal`, and which repository owns runtime brand assets.

## Decision

SecPal is the platform and product family. `GuardGuide by SecPal` is a standalone product in that family and may be shortened to `GuardGuide` after the full relationship is clear in nearby copy.

This repository records shared brand standards, exact public naming rules, and asset-ownership boundaries. Product repositories own runtime configuration, app icons, screenshots, distributable brand assets, and product-specific implementation details.

## Rationale

The family-and-endorsed-product model lets SecPal remain broad enough for future products while giving GuardGuide a standalone public identity.

## Consequences

### Positive

- Contributors have one shared source for product hierarchy and first-mention rules.
- GuardGuide can be marketed as its own product without losing its SecPal relationship.
- Runtime assets remain owned by the product repositories that ship them.

### Negative

- Public copy must be reviewed for correct first mentions and product hierarchy.
- Product repositories may need local follow-up when existing copy treats GuardGuide as a module or feature.

## Alternatives Considered

1. **Name every product as `SecPal <Product>`**
   - Pro: strongest umbrella consistency
   - Contra: makes standalone products look like internal modules
2. **Let each repository define brand hierarchy locally**
   - Pro: low central documentation effort
   - Contra: creates inconsistent public naming across the organization

## Related

- [Brand Architecture](../brand/brand-architecture.md)
- [Naming](../brand/naming.md)
- [Logo Usage](../brand/logo-usage.md)
