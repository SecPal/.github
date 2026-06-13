<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Licensing Wording

SecPal materials use different license wording depending on whether the audience is human or machine-readable tooling.

## Required Wording

| Context                                                         | Use                 | Do not use                                |
| --------------------------------------------------------------- | ------------------- | ----------------------------------------- |
| Human-readable footer or compact public copy                    | `AGPL v3+`          | `AGPL-3.0-or-later`, `AGPLv3+`, `AGPL 3+` |
| SPDX headers, REUSE metadata, package metadata, workflow checks | `AGPL-3.0-or-later` | `AGPL v3+`, `AGPL-3.0+`                   |

## Usage Rules

- Use `Licensed under AGPL v3+` in public footers.
- Use the SPDX expression `AGPL-3.0-or-later` in source file license headers for files that are licensed under the AGPL.
- Use the package ecosystem's SPDX-compatible license field where one exists.
- Do not put human-readable license wording into machine-readable metadata.
- Do not put SPDX expressions into compact public footers unless the surface is specifically about license compliance.

## Rationale

`AGPL v3+` is easier to read in short public copy. `AGPL-3.0-or-later` is the canonical SPDX expression that license scanners, package registries, and REUSE tooling can interpret reliably.
