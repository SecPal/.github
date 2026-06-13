## Codebase Patterns

- Organization-wide documentation in this repository uses SPDX headers and should define repository-agnostic scope boundaries instead of product implementation details.
- Brand standards should document exact public strings separately from implementation assets; product repositories own runtime assets and `.github` owns cross-repository rules.
- Shared design standards should be split by visual concern, while product repositories own exact token values, framework wiring, runtime assets, and component code.
- Application shell and component standards should document shared defaults, approved stacks, and accessibility expectations while product repositories own routing, breakpoints, component APIs, and code wiring.
- ADRs may use story-requested filenames, but their body should still follow the repository ADR sections and record decisions without creating runtime implementation obligations in `.github`.
- Final documentation audits should reconcile section indexes and naming-convention text with the files actually added, especially when a planned layout becomes a current document set.

## US-001: Create the documentation skeleton for brand and design standards

- Implemented `docs/brand/README.md` and `docs/design/README.md` as entry points for the new standards sections.
- Established planned brand and design documentation paths in the section READMEs without adding product-specific implementation content or runtime assets.
- Files changed:
  - `docs/brand/README.md`
  - `docs/design/README.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - New organization-wide docs should include an SPDX comment header and clearly separate shared standards from product repository implementation details.
  - Gotchas encountered
    - Git cannot track empty directories, so the future file layout is documented in the section READMEs until later stories add focused content files.

## US-002: Document SecPal and GuardGuide brand architecture and naming

- Implemented focused brand standards for product hierarchy, naming, slogans, footer wording, logo usage, and licensing wording.
- Documented SecPal as the platform or suite and `GuardGuide by SecPal` as a standalone product in the SecPal family.
- Recorded exact slogan and footer strings, including the rule that slogans do not end with a period.
- Distinguished human-readable footer wording `AGPL v3+` from machine-readable SPDX and package wording `AGPL-3.0-or-later`.
- Clarified that runtime brand assets remain in product repositories while `.github` documents rules and suggested locations only.
- Files changed:
  - `docs/brand/README.md`
  - `docs/brand/brand-architecture.md`
  - `docs/brand/naming.md`
  - `docs/brand/slogans.md`
  - `docs/brand/footer-wording.md`
  - `docs/brand/logo-usage.md`
  - `docs/brand/licensing-wording.md`
  - `.context/progress.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - Brand rules should keep public copy, license compliance wording, and asset ownership in separate focused files.
  - Gotchas encountered
    - Existing public profile copy had a period after the SecPal slogan, so the brand rule now documents the normalized period-free slogan string.

## US-003: Define the shared visual foundation for typography, color, dark mode, and page titles

- Implemented focused design standards for typography, color usage, dark-mode tokens, and browser title patterns.
- Documented Inter as the only default typeface, the allowed weights, no default display font, no global OpenType character variants such as `cv11`, standard size ranges, heading rules, and root rendering defaults.
- Defined neutral zinc or slate UI bases, brand colors as accents, status colors as separate semantic colors, class-based dark mode, required token concepts, and page title patterns with examples.
- Files changed:
  - `docs/design/README.md`
  - `docs/design/typography.md`
  - `docs/design/colors.md`
  - `docs/design/dark-mode.md`
  - `docs/design/page-titles.md`
  - `.context/progress.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - Shared visual rules should document vocabulary and constraints without choosing product-specific token values or framework implementations.
  - Gotchas encountered
    - Page title examples need to preserve the en dash from the standard patterns so implementers do not substitute hyphens inconsistently.

## US-004: Define the shared application shell and component standards

- Implemented focused standards for layout, navigation, components, forms, tables, and accessibility.
- Documented top navigation as the default shell for SecPal and GuardGuide, including desktop topbar, optional breadcrumb or context bar, full-width work area, module tabs, and mobile sheet navigation.
- Defined the approved application UI stack as shadcn/ui, Radix UI, Tailwind CSS, and Lucide icons, with guidance against parallel UI libraries and one-off replacements for standard components.
- Covered keyboard navigation, visible focus states, sufficient contrast, labels and descriptions, clear error states, non-color-only status communication, and Radix-based accessibility patterns for dialogs, dropdowns, sheets, and menus.
- Files changed:
  - `docs/design/README.md`
  - `docs/design/layout.md`
  - `docs/design/navigation.md`
  - `docs/design/components.md`
  - `docs/design/forms.md`
  - `docs/design/tables.md`
  - `docs/design/accessibility.md`
  - `.context/progress.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - Shared application shell guidance should describe navigation regions and expected behavior without prescribing repository-specific route trees, breakpoints, or component APIs.
  - Gotchas encountered
    - Component standards need to name the approved stack directly while still avoiding a false central component package contract.

## US-005: Record the major brand and design decisions as ADRs

- Added six concise accepted ADRs for brand architecture, typography, navigation pattern, footer wording, page titles, and the application UI stack.
- Linked the new numbered ADR files from the existing ADR index while preserving the repository's normal ADR section structure.
- Kept the ADRs documentation-only and aligned them with the brand and design standards without moving runtime ownership out of product repositories.
- Files changed:
  - `docs/adr/0001-brand-architecture.md`
  - `docs/adr/0002-typography.md`
  - `docs/adr/0003-navigation-pattern.md`
  - `docs/adr/0004-footer-wording.md`
  - `docs/adr/0005-page-titles.md`
  - `docs/adr/0006-app-ui-stack.md`
  - `docs/adr/README.md`
  - `.context/progress.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - Numbered ADR series can be added alongside the existing date-based ADR files when the index links them explicitly and the document body keeps the standard ADR sections.
  - Gotchas encountered
    - Existing ADR identifiers already include `ADR-001` through `ADR-013`, so the new four-digit ADR titles should remain visibly tied to the requested brand/design series rather than replacing the older historical ADRs.

## US-006: Perform a documentation consistency and scope audit

- Audited the requested brand, design, and ADR documentation set for file presence, terminology consistency, Markdown formatting, and repository scope.
- Updated the brand and design section READMEs so their layout sections distinguish current standards from future candidate files.
- Updated the ADR README naming convention so the four-digit brand/design ADR series is documented alongside the repository's date-prefixed ADR convention.
- Verified the branch diff remains confined to `.github` documentation paths and does not modify application code, frontend code, API contracts, OpenAPI specs, package files, build configs, runtime assets, `SecPal/contracts`, or other product repositories.
- Files changed:
  - `docs/brand/README.md`
  - `docs/design/README.md`
  - `docs/adr/README.md`
  - `.context/progress.md`
- **Learnings for future iterations:**
  - Patterns discovered
    - Final documentation audits should update index terminology from planned to current once focused files have been added.
    - ADR indexes should explicitly document any accepted filename-series exception instead of leaving it implicit in the links.
  - Gotchas encountered
    - Search-based terminology checks can find invalid brand strings inside explicit `Do not use` examples; those matches need context review rather than automatic removal.
