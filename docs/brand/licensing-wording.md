<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Licensing Wording

SecPal materials use different license wording and different link targets depending on the actual license in use, the audience (human vs. machine-readable tooling), and the surface (compact public footer, legal document, source file, repository documentation).

## Required Wording

| Context                                                              | Use                                              | Do not use                                |
| -------------------------------------------------------------------- | ------------------------------------------------ | ----------------------------------------- |
| Human-readable footer or compact public copy for AGPL-licensed usage | `AGPL v3+`                                       | `AGPL-3.0-or-later`, `AGPLv3+`, `AGPL 3+` |
| Human-readable footer or compact public copy for commercial usage    | wording that matches the active commercial terms | `AGPL v3+`, `AGPL-3.0-or-later`           |
| SPDX headers, REUSE metadata, package metadata, workflow checks      | `AGPL-3.0-or-later`                              | `AGPL v3+`, `AGPL-3.0+`                   |

## Required Link Targets

<!-- REUSE-IgnoreStart -->

| Surface                                                                   | Link target                                                               | Notes                                                                                 |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Product brand footer (`AGPL v3+` label)                                   | `https://www.gnu.org/licenses/agpl-3.0.html`                              | Canonical public AGPL URL. See `footer-wording.md`.                                   |
| CLA, contributor agreement, or other policy document referencing the AGPL | `https://www.gnu.org/licenses/agpl-3.0.html`                              | Same canonical public URL because policy text needs an authoritative external anchor. |
| Repository README, contributor docs, or in-repo "License" section         | the repository's local `LICENSE` file or `LICENSES/AGPL-3.0-or-later.txt` | Lets readers see the exact license bytes shipped with that repository.                |
| SPDX source file header (`SPDX-License-Identifier: AGPL-3.0-or-later`)    | _no URL_                                                                  | SPDX identifiers are URL-free by design; tooling resolves them.                       |
| Package metadata license fields                                           | SPDX-compatible license expression (`AGPL-3.0-or-later`), no URL          | Lets ecosystem tooling reason about the license without parsing HTML.                 |

<!-- REUSE-IgnoreEnd -->

## Usage Rules

- Use `Licensed under AGPL v3+` (or, in the documented two-line footer, the standalone `AGPL v3+` label) only in public footers for AGPL-licensed surfaces.
- Use license wording that matches the active commercial agreement on commercially licensed surfaces.
- Use the SPDX expression `AGPL-3.0-or-later` in source file license headers for files that are licensed under the AGPL.
- Use the package ecosystem's SPDX-compatible license field where one exists.
- Do not put human-readable license wording into machine-readable metadata.
- Do not put SPDX expressions into compact public footers unless the surface is specifically about license compliance.
- Do not link to `https://www.gnu.org/licenses/agpl-3.0.html` from repository README files, in-repo documentation, or in-repo "License" sections; link to the local `LICENSE` file or `LICENSES/AGPL-3.0-or-later.txt` so readers see the exact bytes shipped with that repository.
- Do not embed a URL inside an SPDX header or a package license field; SPDX identifiers are URL-free by design.

## Rationale

`AGPL v3+` is easier to read in short AGPL public copy. `AGPL-3.0-or-later` is the canonical SPDX expression that license scanners, package registries, and REUSE tooling can interpret reliably. Commercially licensed surfaces need public wording that matches the actual commercial terms instead of reusing AGPL wording as a generic label.

The public AGPL URL `https://www.gnu.org/licenses/agpl-3.0.html` is reserved for surfaces that need an authoritative external anchor for the license — namely product brand footers and policy documents such as the CLA. Repository-internal references point at the local `LICENSE` file or `LICENSES/` folder so readers see the exact license text shipped with that repository, including any SPDX-formatted license bundle.
