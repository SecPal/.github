<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Colors

SecPal interfaces use a neutral UI base with product brand colors as accents. Product repositories own exact token values and implementation details, but shared color usage should follow the boundaries in this document.

## Neutral Base

Use zinc or slate as the neutral UI base for application chrome, page backgrounds, cards, borders, dividers, muted text, and default foreground text. The chosen neutral family should be applied consistently within a product surface.

Do not use product brand colors as general-purpose body text, default headings, default borders, or large neutral backgrounds. Core readability should come from the neutral scale.

## Brand Accents

Product brand colors are accents. Use them for selected navigation states, primary calls to action, key focus moments, product identity details, and limited visual emphasis.

Brand colors should not replace semantic status colors. A product accent can support recognition, but it should not be the only cue for success, warning, error, or destructive states.

## Status Colors

Keep status colors separate from brand colors.

- Success communicates completion, availability, or verified state.
- Warning communicates risk, pending attention, or degraded state.
- Destructive communicates removal, irreversible actions, or serious failure.
- Informational communicates neutral system feedback when no stronger status applies.

Status colors must remain legible in light and dark mode and should be paired with text, iconography, or shape where color alone would be ambiguous.

## Contrast And Use

Text, icons, borders, rings, and disabled states must meet the contrast expectations of the owning product surface. Avoid low-contrast brand-on-brand combinations, especially on generated documents and public promotional pages where users cannot adjust the theme.
