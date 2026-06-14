<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Footer Wording

Use this footer pattern on every AGPL-licensed public product surface that needs compact brand, attribution, and license wording.

## Approved Footer Pattern

The footer has two stacked lines.

**Line 1 — brand attribution (linked to the brand's homepage):**

```text
Powered by <Brand> – <Slogan>
```

**Line 2 — license and source links, each preceded by its icon:**

```text
<license-icon> AGPL v3+   <source-icon> <Source Code label>
```

## Approved Footer Strings

### SecPal Platform Or Suite Surface

- **Line 1**: `Powered by SecPal – A guard's best friend`
  - Linked to: `https://secpal.app`
- **Line 2**: `AGPL v3+` plus the localized source-code label
  - `AGPL v3+` linked to: `https://www.gnu.org/licenses/agpl-3.0.html`
  - Source-code link target: `https://github.com/SecPal`

### GuardGuide Product Surface

- **Line 1**: `Powered by GuardGuide – A guard's source of truth`
  - Linked to: `https://guardguide.de`
- **Line 2**: `AGPL v3+` plus the localized source-code label
  - `AGPL v3+` linked to: `https://www.gnu.org/licenses/agpl-3.0.html`
  - Source-code link target: `https://github.com/SecPal/GuardGuide`

## Usage Rules

### Brand Attribution Line

- Use the exact wording `Powered by <Brand> – <Slogan>` with the brand name and slogan exactly as documented in `slogans.md`.
- Use the en-dash `–` (U+2013) with **one space on each side** between brand and slogan. Do not substitute a hyphen-minus (`-`, U+002D) or an em dash (`—`, U+2014). See `slogans.md` § "Separator Rule".
- Do not translate the `Powered by` prefix or the slogan, even on German-language pages or other localized surfaces.
- Each surface uses its own brand: SecPal pages use `Powered by SecPal`, GuardGuide pages use `Powered by GuardGuide`. Do not write `Powered by SecPal` on GuardGuide surfaces, and do not write `Powered by GuardGuide` on SecPal surfaces.
- The entire line 1 string is the link target's link text and points to the brand's homepage (`https://secpal.app` or `https://guardguide.de`).

### License And Source Line

- Use the public AGPL link target `https://www.gnu.org/licenses/agpl-3.0.html` for the `AGPL v3+` label in compact public footers. See `licensing-wording.md` for the full link-target rule.
- Use the localized source-code label for the source link. Translate this label to the page's language using the canonical local two-word term for "source code": English `Source Code`, German `Quellcode`, and the canonical local term in every other supported locale. Do not abbreviate to a one-word form such as `Source` (English) or `Quelle` / `Quelltext` (German). The link target itself does not change with locale.
- Use the source-code link target documented per brand above. The SecPal footer points at the SecPal GitHub organization because the SecPal platform spans multiple repositories; the GuardGuide footer points at the GuardGuide product repository because that product has a single repository.
- Precede each label with its appropriate icon from the product repository's documented icon system: a license/legal glyph for `AGPL v3+`, and a source-control glyph for the source-code link.

### General

- Use this pattern only on AGPL-licensed public surfaces. Commercially licensed surfaces must adjust the license label to wording that matches the active commercial terms (see `licensing-wording.md`), but keep the line-1 brand attribution and the source-code link unchanged.
- Product repositories may adapt visual layout, separators between line-2 items, responsive wrapping, and icon styling, but must preserve the exact strings, link targets, separator characters, and language rules above.

## Rationale

A two-line footer keeps brand attribution and legal/source attribution visually separate while staying compact enough for every surface. The `Powered by <own brand> – <own slogan>` line is the recognisable brand signature that travels unchanged across languages. The second line satisfies the AGPL's source-availability and license-disclosure expectations using the canonical public license URL and the canonical public source location for each product, while letting the source-code label localize to the reader.

Linking the AGPL label to `https://www.gnu.org/licenses/agpl-3.0.html` rather than to a repo-local snapshot guarantees readers always reach the canonical, up-to-date license text the AGPL itself references.
