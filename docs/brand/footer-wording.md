<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Footer Wording

This is the canonical SecPal and GuardGuide public footer pattern. Use it on every AGPL-licensed public product surface that needs compact brand, license, and source attribution.

## Approved Footer Pattern

The footer has two stacked lines.

**Footer line 1** (brand attribution, linked to the brand's homepage):

```text
Powered by <Product> – <Slogan>
```

**Footer line 2** (license and source-code links):

```text
AGPL v3+ | <Source Code label>
```

## Approved Footer Strings

### SecPal

German:

```text
Powered by SecPal – A guard's best friend
AGPL v3+ | Quellcode
```

English:

```text
Powered by SecPal – A guard's best friend
AGPL v3+ | Source Code
```

### GuardGuide

German:

```text
Powered by GuardGuide – A guard's source of truth
AGPL v3+ | Quellcode
```

English:

```text
Powered by GuardGuide – A guard's source of truth
AGPL v3+ | Source Code
```

## Link Targets

| Element                     | SecPal                                       | GuardGuide                                   |
| --------------------------- | -------------------------------------------- | -------------------------------------------- |
| Footer line 1 (entire line) | `https://secpal.app`                         | `https://guardguide.de`                      |
| `AGPL v3+` label            | `https://www.gnu.org/licenses/agpl-3.0.html` | `https://www.gnu.org/licenses/agpl-3.0.html` |
| Source Code label           | `https://github.com/SecPal`                  | `https://github.com/SecPal/GuardGuide`       |

The SecPal Source Code link points at the SecPal GitHub organization because the SecPal platform spans multiple repositories. The GuardGuide Source Code link points at the GuardGuide product repository because that product has a single repository.

## Separator Rules

- **Slogan separator (line 1)**: EN DASH `–` (U+2013) with **one space on each side**. Do not use hyphen-minus (`-`, U+002D) or em dash (`—`, U+2014). See `slogans.md` § "Separator Rule".
- **License/Source-Code separator (line 2)**: vertical bar `|` (U+007C) with **one space on each side**. Do not omit the spaces and do not use a different separator character such as `/`, `·`, `•`, or `,`.
- **No period at the end of the slogan**.

## Language Rules

- The `Powered by` prefix, the brand name, the slogan, and the `AGPL v3+` label stay English on every surface and locale, including German-language pages.
- The Source Code label is localized to the page's language using the canonical local two-word term for "source code":
  - English: `Source Code`
  - German: `Quellcode`
  - Other locales: the canonical local two-word term
- Do not abbreviate the Source Code label to a one-word form such as `Source` (English) or `Quelle` / `Quelltext` (German).
- The Source Code link target does not change with locale.

## Usage Rules

- Use the exact strings shown above for SecPal and GuardGuide. Each surface uses its own brand: SecPal pages use `Powered by SecPal`, GuardGuide pages use `Powered by GuardGuide`. Do not write `Powered by SecPal` on GuardGuide surfaces, and do not write `Powered by GuardGuide` on SecPal surfaces.
- Use the public AGPL link target `https://www.gnu.org/licenses/agpl-3.0.html` for the `AGPL v3+` label in compact public footers. See `licensing-wording.md` for the full link-target rule.
- Use this pattern only on AGPL-licensed public surfaces. Commercially licensed surfaces must adjust the license label to wording that matches the active commercial terms (see `licensing-wording.md`), but keep the line-1 brand attribution and the Source Code link unchanged.
- Product repositories may adapt visual layout, responsive wrapping, typography, and may render an optional icon before each label on line 2 (a license/legal glyph for `AGPL v3+`, a source-control glyph for the Source Code link). The exact text strings, the `|` separator, the spaces around the `|`, and the link targets must remain unchanged.

## Rationale

A two-line footer keeps brand attribution and legal/source attribution visually separate while staying compact enough for every surface. The `Powered by <own brand> – <own slogan>` line is the recognisable brand signature that travels unchanged across languages. The second line satisfies the AGPL's source-availability and license-disclosure expectations using the canonical public license URL and the canonical public source location for each product, while letting the Source Code label localize to the reader.

Linking the `AGPL v3+` label to `https://www.gnu.org/licenses/agpl-3.0.html` rather than to a repo-local snapshot guarantees readers always reach the canonical, up-to-date license text the AGPL itself references.
