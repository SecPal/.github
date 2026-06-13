<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Design Standards

This section contains organization-wide design standards for SecPal.

Use these documents for shared product and interface design guidance that helps SecPal repositories make consistent decisions. Repository-specific UI implementation details, framework choices, tokens, and component code belong in the product repository that owns them.

## Scope

Design standards may cover:

- shared design principles
- accessibility expectations
- interaction patterns
- layout and information architecture guidance
- content structure for user-facing interfaces
- cross-product consistency rules

Design standards do not cover:

- product-specific component APIs
- CSS, native, or web implementation details
- repository-local design token build systems
- screen-by-screen product specifications
- runtime assets or generated application files

## Document Layout

Current design standards live under this directory:

- `docs/design/README.md` - section entry point and scope boundary
- `docs/design/typography.md` - shared typeface, scale, and rendering rules
- `docs/design/colors.md` - shared color usage boundaries
- `docs/design/dark-mode.md` - shared dark-mode token requirements
- `docs/design/page-titles.md` - shared browser title patterns
- `docs/design/accessibility.md` - accessibility standards and review expectations
- `docs/design/components.md` - approved application UI stack and component standards
- `docs/design/forms.md` - shared form structure, validation, and state guidance
- `docs/design/layout.md` - layout and information architecture guidance
- `docs/design/navigation.md` - shared application shell and navigation patterns
- `docs/design/tables.md` - table layout, interaction, and accessibility guidance

Future design standards may include:

- `docs/design/principles.md` - shared design principles
- `docs/design/interaction-patterns.md` - reusable interaction behavior guidance
- `docs/design/content.md` - user-facing content structure and writing patterns

Add new design standards here only when they describe reusable organization-wide guidance.
