<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# BRAND-0004: Footer Wording

## Status

**Accepted**

## Date

2026-06-13

## Deciders

SecPal maintainers

## Context

Public product surfaces need a compact footer that combines brand identity, slogan text, a public AGPL license link, and a public source-code link. Contributors also need a clear distinction between AGPL public copy, commercial-license copy, machine-readable license identifiers, and the link targets used for the public AGPL URL versus the in-repo `LICENSE` file.

Without a fixed pattern, each product surface would re-invent small but visible details — slogan punctuation, separator characters, the language of the `Powered by` prefix, whether the AGPL footer points at `gnu.org` or a repo-local snapshot, and whether the source-code label is translated.

## Decision

SecPal and GuardGuide use a fixed two-line footer on every AGPL-licensed public surface.

**Line 1 — brand attribution:** `Powered by <Brand> – <Slogan>`, linked to the brand's homepage.

- SecPal: `Powered by SecPal – A guard's best friend`, linked to `https://secpal.app`.
- GuardGuide: `Powered by GuardGuide – A guard's source of truth`, linked to `https://guardguide.de`.
- Each surface uses its own brand. The GuardGuide footer says `Powered by GuardGuide`, not `Powered by SecPal`, because the footer line targets GuardGuide's own homepage.
- The separator between brand and slogan is the en-dash `–` (U+2013) with one space on each side. Hyphen-minus and em dash are not allowed.
- The `Powered by` prefix and the slogan are never translated.

**Line 2 — license and source links:** the `AGPL v3+` label linked to `https://www.gnu.org/licenses/agpl-3.0.html`, plus a localized source-code label linked to the product's GitHub location.

- SecPal source-code label points at the SecPal GitHub organization (`https://github.com/SecPal`) because the SecPal platform spans multiple repositories.
- GuardGuide source-code label points at the GuardGuide product repository (`https://github.com/SecPal/GuardGuide`).
- The source-code label is the canonical local term for "source code" in the page's language (English `Source`, German `Quelltext`, and so on). The link target does not change with locale.
- Each label is preceded by its icon from the product repository's documented icon system (a license/legal glyph for `AGPL v3+`, a source-control glyph for the source-code link).

Commercially licensed or otherwise non-AGPL surfaces must adjust the license label to wording that matches the active license terms instead of reusing `AGPL v3+`, but keep the line-1 brand attribution and the source-code link unchanged.

Machine-readable contexts continue to use `AGPL-3.0-or-later` for SPDX headers, package metadata, license scanners, and license fields, with no URL embedded.

## Rationale

A fixed two-line footer keeps brand attribution visually separate from legal/source attribution while remaining compact enough for every surface. Each brand owning its own `Powered by <own brand>` line matches the link target on that line and gives every product a recognisable signature that travels unchanged across languages. Linking the `AGPL v3+` label to `https://www.gnu.org/licenses/agpl-3.0.html` rather than a repo-local snapshot guarantees readers always reach the canonical, up-to-date license text. Localizing the source-code label while keeping the link target stable lets the footer read naturally in every locale without losing the public source pointer the AGPL requires.

## Consequences

### Positive

- AGPL public footers remain consistent across websites, application surfaces, and generated materials.
- License wording is readable for humans while SPDX metadata remains precise for tools.
- Slogan punctuation, separator characters, and link targets stay consistent with the broader brand standards.
- Readers can always reach the canonical AGPL text and the canonical public source repository from any product footer.

### Negative

- Product repositories must preserve the approved AGPL words, the approved slogan, the en-dash separator, the link targets, and the icon-plus-label structure exactly, even when adapting layout, separators, or responsive wrapping.
- Commercial deployments still need repository-local license wording that matches the actual agreement.
- Existing public surfaces may need copy-only updates to adopt the two-line layout, the `Powered by <own brand>` self-attribution, the en-dash lockup, the corrected GuardGuide slogan, and the localized source-code label.

## Alternatives Considered

1. **Let products write footer copy locally**
   - Pro: local copy can fit each layout exactly
   - Contra: creates inconsistent license wording, slogan punctuation, separator characters, and link targets
2. **Use only SPDX license identifiers in footers**
   - Pro: precise and scanner-friendly
   - Contra: less readable as public brand copy
3. **One shared `Powered by SecPal` line on every product footer (including GuardGuide)**
   - Pro: highlights the SecPal platform on every surface
   - Contra: mismatched the line-1 link target (each footer line should point at its own brand's homepage and source) and removed each product's own signature from its own footer

## Related

- [Footer Wording](../brand/footer-wording.md)
- [Slogans](../brand/slogans.md)
- [Licensing Wording](../brand/licensing-wording.md)
- [Brand Architecture](../brand/brand-architecture.md)
