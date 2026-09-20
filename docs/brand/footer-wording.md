<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Footer Wording

This is the canonical current SecPal public footer pattern. Use it on
AGPL-licensed public SecPal product surfaces that need compact brand, license,
and source attribution.

No product-specific footer or slogan is approved for SecPal Assure or SecPal
Visit. Naming authority does not create a footer, homepage, or source
repository for either specialist product.

## Approved Footer Pattern

The footer has two stacked lines.

**Footer line 1** (brand attribution, linked to the applicable SecPal homepage):

```text
Powered by SecPal – A guard's best friend
```

**Footer line 2** (license and source-code links):

```text
AGPL v3+ | <Source Code label>
```

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

## Link Targets

| Element                     | Link target                                     |
| --------------------------- | ----------------------------------------------- |
| Footer line 1 (entire line) | `https://secpal.app`                            |
| `AGPL v3+` label            | `https://www.gnu.org/licenses/agpl-3.0.html`    |
| Source Code label           | public source repository for the owning surface |

The Source Code link is per surface. It points to the canonical public source
repository that backs the rendered surface. For the SecPal organization or
family as a whole, where no single repository backs the complete surface, use
`https://github.com/SecPal`. The SecPal landing page uses
`https://github.com/SecPal/secpal.app`.

Do not infer an Assure or Visit source link from the approved product name. Add
a product-specific mapping only when an owning public surface and its canonical
source repository are established by current evidence.

## Separator Rules

- **Slogan separator (line 1):** EN DASH `–` (U+2013) with one space on each
  side. Do not use hyphen-minus (`-`, U+002D) or em dash (`—`, U+2014).
- **License/source separator (line 2):** vertical bar `|` (U+007C) with one
  space on each side.
- **No period at the end of the slogan.**

## Language Rules

- The `Powered by` prefix, brand name, slogan, and `AGPL v3+` label stay English
  on every surface and locale.
- Localize the Source Code label to the page language: English `Source Code`,
  German `Quellcode`, or the canonical local term in another supported locale.
- Do not use abbreviated or informal forms such as `Source`, `Quelle`, or
  `Quelltext`.
- The Source Code link target does not change with locale.

## Usage Rules

- The first line is official branding for SecPal-maintained surfaces, not an
  additional AGPL license condition. The second line communicates the
  applicable license and source location; neither line changes the license text.
- Use the public AGPL link target shown above. See `licensing-wording.md` for the
  full link-target rule.
- Use this pattern only on AGPL-licensed public surfaces. A commercially
  licensed surface must use license wording that matches its active terms.
- Owning repositories may adapt layout, responsive wrapping, typography, and
  optional line-2 icons. The exact text, separators, spacing, and authenticated
  link targets remain unchanged.

## Rationale

A two-line footer keeps official SecPal identity separate from legal and source
information. Per-surface source links take readers to the source that actually
backs the surface without inventing repository mappings from product strategy.
