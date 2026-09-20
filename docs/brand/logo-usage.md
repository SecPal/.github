<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Logo Usage

This repository documents logo usage rules only. Runtime brand assets remain in
owning product repositories, and `.github` must not become the source for
production app icons, website images, generated assets, or packaged logo files.

## Usage Rules

- Use the approved SecPal logo for the organization, product family, main
  product, organization profile, and shared governance surfaces where a logo is
  needed.
- No distinct logo or lockup asset is approved here for SecPal Assure or SecPal
  Visit. Use the exact text name when an approved asset does not exist.
- Naming a specialist product does not authorize contributors to derive,
  redraw, or infer an icon, wordmark, monogram, color treatment, or lockup.
- Do not redraw, recolor, stretch, crop, or place effects on the SecPal logo
  unless an owning repository has an approved asset for that exact use.
- Keep clear space around logos in public surfaces; do not place logos inside
  dense text, badges, or status indicators.
- Prefer text names over logos in contributor documentation when the asset
  itself is not needed.
- Do not use retired product assets as current SecPal-family identity.

## Suggested Asset Locations

Owning repositories should keep runtime brand assets close to the surface that
ships them. Suggested locations include:

- `public/brand/` for web-served static assets;
- `src/assets/brand/` for frontend source assets;
- `assets/brand/` for mobile or native application assets; and
- `docs/assets/brand/` for documentation-only examples in an owning repository.

These paths are suggestions, not requirements. A repository may choose another
location when its framework or build pipeline has a stronger convention.

## Rationale

Keeping `.github` as the rules repository prevents stale production assets from
spreading across products. Owning repositories can version, optimize, and review
the exact files that ship with their surfaces, while central naming authority
does not manufacture artwork.
