<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Footer Wording

Use these footer strings when an AGPL-licensed public product surface needs compact brand and license wording.

## Approved Footer Strings

SecPal platform or suite surface:

```text
SecPal – A guard's best friend | Licensed under AGPL v3+
```

GuardGuide product surface (with platform attribution):

```text
GuardGuide – A guard's source of truth | Powered by SecPal | Licensed under AGPL v3+
```

License-only compact footer:

```text
Licensed under AGPL v3+
```

## Usage Rules

- Use these examples only on AGPL-licensed public surfaces.
- Use the brand name followed by an en-dash (`–`, U+2013) and the exact approved slogan from `slogans.md`, with no trailing period on the slogan.
- For GuardGuide footers, attribute the platform with the exact wording `Powered by SecPal` as a separate footer segment placed between the brand-plus-slogan lockup and the license wording.
- Use `AGPL v3+` only for human-readable AGPL footer wording.
- Use `AGPL-3.0-or-later` for SPDX headers, package metadata, license scanners, and machine-readable license fields.
- Commercially licensed or otherwise non-AGPL surfaces must use wording that matches the actual license terms for that deployment, but still use the approved English slogan and the `Powered by SecPal` attribution on GuardGuide surfaces.
- Do not translate the slogan or the `Powered by SecPal` credit, even on German-language pages or other localized surfaces.
- Product repositories may adapt layout, separators, and responsive wrapping, but AGPL-licensed surfaces should keep the approved brand wording, slogan, attribution credit, and English language unchanged.

## Rationale

AGPL footers need to be short and readable, so the license appears as `AGPL v3+`. Technical metadata needs a precise SPDX expression, so it uses `AGPL-3.0-or-later` instead. Other licensing models need their own accurate public wording.

The `Powered by SecPal` attribution acknowledges that GuardGuide is a SecPal-family product in compact footer space without forcing the long-form `GuardGuide by SecPal` lockup into every footer cell. Keeping it as a separate, untranslated segment makes the platform relationship visible regardless of page language.
