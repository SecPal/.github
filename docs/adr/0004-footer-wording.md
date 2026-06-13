<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-0004: Footer Wording

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

Public product surfaces need compact footer wording that combines brand identity, slogan text, and human-readable license information. Contributors also need a clear distinction between public copy and machine-readable license identifiers.

## Decision

SecPal and GuardGuide use the exact approved footer strings documented in the brand standards. Public footer copy uses slogan text without trailing periods and uses `AGPL v3+` for compact human-readable license wording.

Machine-readable contexts continue to use `AGPL-3.0-or-later` for SPDX headers, package metadata, license scanners, and license fields.

## Rationale

Fixed footer strings prevent small punctuation, naming, and license wording differences from spreading across public surfaces.

## Consequences

### Positive

- Public footers remain consistent across websites, application surfaces, and generated materials.
- License wording is readable for humans while SPDX metadata remains precise for tools.
- Slogan punctuation stays consistent with the broader brand standards.

### Negative

- Product repositories must preserve the approved words even when adapting layout or responsive wrapping.
- Existing public surfaces may need copy-only updates.

## Alternatives Considered

1. **Let products write footer copy locally**
   - Pro: local copy can fit each layout exactly
   - Contra: creates inconsistent license and slogan wording
2. **Use only SPDX license identifiers in footers**
   - Pro: precise and scanner-friendly
   - Contra: less readable as public brand copy

## Related

- [Footer Wording](../brand/footer-wording.md)
- [Slogans](../brand/slogans.md)
- [Licensing Wording](../brand/licensing-wording.md)
