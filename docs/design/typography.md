<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Typography

Inter is the primary and only default typeface for SecPal, GuardGuide, changelog, promotional sites, generated documents, and shared contributor-facing materials.

Use Inter for body text, headings, navigation, controls, data tables, labels, and generated PDF or document text. Product repositories should self-host Inter where the surface ships fonts directly, subject to license and platform constraints. Do not rely on remote font CDNs for production product interfaces when self-hosting is practical.

## Font Family

- Default family: `Inter`
- Fallback stack: product repositories may define system fallbacks after Inter for platform resilience.
- Allowed weights: `400`, `500`, `600`, and `700`
- Default display font: none

Do not introduce a separate default display, heading, marketing, mono, or document font unless a product-specific exception is documented in the owning repository. Code editors, terminal blocks, and machine-readable identifiers may use repository-local monospace stacks where needed.

## OpenType Features

Do not set global OpenType character variants, including `cv11`. Product repositories may use localized or component-scoped font feature settings only when a specific readability or language requirement justifies the exception.

Default text should not depend on discretionary ligatures, stylistic sets, or character variants to carry the brand.

## Size Ranges

Use a restrained type scale that keeps operational interfaces dense and readable.

| Use              | Standard range |
| ---------------- | -------------- |
| Supporting text  | `12px`-`14px`  |
| Body text        | `14px`-`16px`  |
| UI labels        | `12px`-`14px`  |
| Controls         | `14px`-`16px`  |
| Page headings    | `24px`-`36px`  |
| Section headings | `18px`-`24px`  |
| Document titles  | `28px`-`40px`  |

Generated documents may use point sizes that map to the same relative hierarchy. Promotional pages may use larger title sizes only when the first viewport needs a true marketing or editorial hierarchy.

## Weight And Tracking

- Body text uses `400`.
- Emphasized body text, labels, and compact navigation use `500`.
- Section headings use `600`.
- Page titles and document titles use `600` or `700`.
- Avoid global letter spacing. Use `letter-spacing: 0` as the default.
- Do not use negative tracking for headings.
- Use uppercase text sparingly; when uppercase labels are required, keep them short and maintain readable spacing in the owning product styles.

## Rendering Defaults

Product repositories should set these rendering defaults at the root of the application or document stylesheet where the target platform supports them:

```css
font-synthesis: none;
text-rendering: optimizeLegibility;
-webkit-font-smoothing: antialiased;
-moz-osx-font-smoothing: grayscale;
```

Repository-local styles may adapt the syntax for native applications, generated documents, or framework-specific root elements, but the rendered result should keep Inter crisp, stable, and consistent across surfaces.
