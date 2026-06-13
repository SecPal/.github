<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Footer Wording

Use these exact footer strings when a public product surface needs compact brand and license wording.

## Approved Footer Strings

SecPal platform or suite surface:

```text
SecPal - A guard's best friend | Licensed under AGPL v3+
```

GuardGuide product surface:

```text
GuardGuide by SecPal - Clear instructions for every shift | Licensed under AGPL v3+
```

License-only compact footer:

```text
Licensed under AGPL v3+
```

## Usage Rules

- Use `AGPL v3+` only for human-readable footer wording.
- Use `AGPL-3.0-or-later` for SPDX headers, package metadata, license scanners, and machine-readable license fields.
- Do not add a period to the slogan portion of a footer string.
- Keep `GuardGuide by SecPal` in the GuardGuide footer even when the surrounding page already mentions SecPal.
- Product repositories may adapt layout, separators, and responsive wrapping, but the words must remain unchanged.

## Rationale

Footers need to be short and readable, so the license appears as `AGPL v3+`. Technical metadata needs a precise SPDX expression, so it uses `AGPL-3.0-or-later` instead.
