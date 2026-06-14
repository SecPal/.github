<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Logo Usage

This repository documents logo usage rules only. Runtime brand assets remain in product repositories, and `.github` must not become the source for production app icons, website images, generated assets, or packaged logo files.

## Usage Rules

- Use the SecPal logo for the platform, suite, organization profile, and shared governance surfaces.
- Use the GuardGuide by SecPal product lockup for GuardGuide public surfaces when a product logo or wordmark is needed.
- Do not redraw, recolor, stretch, crop, or place effects on logos unless a product repository has an approved asset for that exact use.
- Do not use the SecPal logo alone where the user needs to identify the GuardGuide product specifically.
- Keep clear space around logos in public surfaces; do not place logos inside dense text, badges, or status indicators.
- Prefer text names over logos in contributor documentation when the asset itself is not needed.

## Suggested Asset Locations

Product repositories should keep runtime brand assets close to the surface that ships them. Suggested locations include:

- `public/brand/` for web-served static assets
- `src/assets/brand/` for frontend source assets
- `assets/brand/` for mobile or native application assets
- `docs/assets/brand/` for documentation-only examples in a product repository

These paths are suggestions, not requirements. A product repository may choose another location when its framework or build pipeline has a stronger convention.

## Rationale

Keeping `.github` as the rules repository prevents stale production assets from spreading across products. Product repositories can version, optimize, and review the exact files that ship with their own application surfaces.
