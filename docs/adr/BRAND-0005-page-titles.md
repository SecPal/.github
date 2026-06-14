<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# BRAND-0005: Page Titles

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

Browser titles and generated document titles appear in tabs, bookmarks, search results, previews, and exported files. Without a shared pattern, products can drift on title order, product naming, separators, and whether slogans or environment labels appear in document titles.

## Decision

Page and document titles identify the current content first, then the product, using a spaced en dash between title parts. The shared patterns are `<Page title> – <Product>`, `<Entity name> – <Section> – <Product>`, and `<Product>` when no stable page or entity title exists.

Product names must match the brand standards, including `GuardGuide by SecPal` unless the owning repository documents a route-specific exception.

## Rationale

Content-first titles are easier to scan in browser tabs and histories, while the final product segment keeps the SecPal or GuardGuide context visible.

## Consequences

### Positive

- Titles remain predictable across tabs, exports, previews, and generated documents.
- The product relationship stays visible without adding slogans to every title.
- The en dash separator avoids inconsistent hyphen punctuation.

### Negative

- Implementations must preserve the en dash character in title formatting.
- Product repositories need local judgment for rare operational exceptions such as environment labels.

## Alternatives Considered

1. **Product-first title order**
   - Pro: emphasizes the brand first
   - Contra: makes many open tabs harder to distinguish
2. **Include slogans in browser titles**
   - Pro: repeats brand copy more often
   - Contra: adds noise and weakens task scanning

## Related

- [Page Titles](../design/page-titles.md)
- [Naming](../brand/naming.md)
