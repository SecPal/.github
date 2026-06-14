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

**Footer line 1 — brand attribution:** `Powered by <Product> – <Slogan>`, linked to the brand's homepage.

- SecPal: `Powered by SecPal – A guard's best friend`, linked to `https://secpal.app`.
- GuardGuide: `Powered by GuardGuide – A guard's source of truth`, linked to `https://guardguide.de`.
- Each surface uses its own brand. The GuardGuide footer says `Powered by GuardGuide`, not `Powered by SecPal`, because the footer line targets GuardGuide's own homepage.
- The separator between brand and slogan is the en-dash `–` (U+2013) with one space on each side. Hyphen-minus (`-`, U+002D) and em dash (`—`, U+2014) are not allowed.
- The `Powered by` prefix and the slogan are never translated.

**Footer line 2 — license and source-code links:** `AGPL v3+ | <Source Code label>`.

- `AGPL v3+` is linked to `https://www.gnu.org/licenses/agpl-3.0.html`.
- The Source Code label is linked to the product's public source location: SecPal points at the SecPal GitHub organization (`https://github.com/SecPal`) because the SecPal platform spans multiple repositories; GuardGuide points at the GuardGuide product repository (`https://github.com/SecPal/GuardGuide`).
- The Source Code label is the canonical local two-word term for "source code" in the page's language: English `Source Code`, German `Quellcode`, and the canonical local term in every other supported locale. Do not abbreviate to a one-word form such as `Source`, `Quelle`, or `Quelltext`. The link target does not change with locale.
- The separator between the two labels is the vertical bar `|` (U+007C) with one space on each side. Other separator characters and missing spaces are not allowed.
- The `AGPL v3+` label stays English on every surface and locale.
- Product repositories may render an optional icon before each line-2 label (a license/legal glyph for `AGPL v3+`, a source-control glyph for the Source Code link), but the exact text strings, the `|` separator, the spaces around the `|`, and the link targets must remain unchanged.

Commercially licensed or otherwise non-AGPL surfaces must adjust the license label to wording that matches the active license terms instead of reusing `AGPL v3+`, but keep the line-1 brand attribution and the Source Code link unchanged.

Machine-readable contexts continue to use `AGPL-3.0-or-later` for SPDX headers, package metadata, license scanners, and license fields, with no URL embedded.

## Rationale

A fixed two-line footer keeps brand attribution visually separate from legal/source attribution while remaining compact enough for every surface. Each brand owning its own `Powered by <own brand>` line matches the link target on that line and gives every product a recognisable signature that travels unchanged across languages. Linking the `AGPL v3+` label to `https://www.gnu.org/licenses/agpl-3.0.html` rather than a repo-local snapshot guarantees readers always reach the canonical, up-to-date license text. Localizing the Source Code label while keeping the link target stable lets the footer read naturally in every locale without losing the public source pointer the AGPL requires.

A text-first standard (with the `|` separator visible as a character, and icons as an optional product-level visual addition) keeps the `.github` standard implementable on every surface — including text-only contexts such as plain-text README footers, generated PDFs, and screen-reader transcripts — without forcing every product repository to depend on a specific icon system.

## Consequences

### Positive

- AGPL public footers remain consistent across websites, application surfaces, generated documents, and text-only contexts.
- License wording is readable for humans while SPDX metadata remains precise for tools.
- Slogan punctuation, separator characters, and link targets stay consistent with the broader brand standards.
- Readers can always reach the canonical AGPL text and the canonical public source repository from any product footer.

### Negative

- Product repositories must preserve the approved AGPL words, the approved slogan, the en-dash separator, the `|` line-2 separator and its surrounding spaces, the link targets, and the language rules exactly, even when adapting visual layout, responsive wrapping, or optional icons.
- Commercial deployments still need repository-local license wording that matches the actual agreement.
- Existing public surfaces may need copy-only updates to adopt the two-line layout, the `Powered by <own brand>` self-attribution, the en-dash lockup, the corrected GuardGuide slogan, the `|` separator with surrounding spaces, and the two-word localized Source Code label.

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
4. **Prescribe a specific icon system in the `.github` standard**
   - Pro: visually identical line 2 across every product
   - Contra: forces every product repository to adopt one icon library and breaks text-only contexts such as plain-text README footers, generated PDFs, and screen-reader transcripts; icons are kept as an optional product-level visual addition instead

## Related

- [Footer Wording](../brand/footer-wording.md)
- [Slogans](../brand/slogans.md)
- [Licensing Wording](../brand/licensing-wording.md)
- [Brand Architecture](../brand/brand-architecture.md)
