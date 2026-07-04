<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Licensing Policy

This document is the central SecPal policy for contributor licensing, SPDX/REUSE metadata, and AGPL attribution terms across shared repositories such as `api`, `frontend`, and `android`.

## Defined Terms

- **SecPal** means the SecPal open source project maintained by the Project Maintainer.
- **Project Maintainer** means the person or legal entity designated in SecPal governance documentation as responsible for accepting contributions, administering contributor agreements, and granting commercial licenses for the SecPal project, including any legal successor or entity to which those rights are assigned.
- **CLA rights recipient** means SecPal acting through the Project Maintainer unless and until SecPal publicly designates a successor legal entity in its governance documentation.

These definitions keep the CLA model as a license grant rather than a copyright assignment: contributors retain copyright ownership and grant SecPal the rights needed for AGPL distribution and commercial relicensing.

## Standard SPDX Copyright Policy

Use project-based copyright notices for SecPal-owned material:

```text
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution
```

For files first published in 2026:

```text
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution
```

Rules:

- Use `SecPal Contributors` for project-owned source code, policy documents, and other repository-owned material.
- Do not use `SecPal` alone as the copyright holder for project-owned code unless SecPal later publishes a clear legal entity or other documented rights holder for that specific use.
- Keep third-party notices separate. Do not replace upstream names, bundled notices, or vendor copyright statements with `SecPal Contributors`.
- Do not switch third-party or externally-authored notices to `SecPal Contributors` just for consistency.

## When To Use `LicenseRef-SecPal-Attribution`

Use `LicenseRef-SecPal-Attribution` only for SecPal-owned AGPL-covered files or REUSE annotations that are intentionally subject to the SecPal attribution addendum.

Rules:

- Pair it only with `AGPL-3.0-or-later` in the same SPDX expression:

  ```text
  AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution
  ```

- Ship the approved addendum text as [`LICENSES/LicenseRef-SecPal-Attribution.txt`](../LICENSES/LicenseRef-SecPal-Attribution.txt).
- Do not use `LicenseRef-SecPal-Attribution` by itself.
- Do not apply it to third-party code, third-party assets, or unrelated custom-license material.
- Do not use it for CC0, MIT, Apache-2.0, or other non-AGPL repository files.

## Third-Party And Tailwind Rules

- Third-party notices must remain under their original licensing and attribution terms.
- Keep third-party REUSE metadata separate from SecPal-owned metadata.
- Do not add Tailwind-specific licensing terms to `api`, `frontend`, or `android` unless Tailwind-derived material is actually present in that repository.
- If Tailwind-derived material is present, keep that handling repository-specific and separate from the SecPal attribution addendum.

## SecPal Attribution Terms

The approved attribution addendum is stored in [`LICENSES/LicenseRef-SecPal-Attribution.txt`](../LICENSES/LicenseRef-SecPal-Attribution.txt).

Summary:

- Required attribution for unmodified interactive AGPL-covered SecPal works: `Powered by SecPal`
- Required attribution for modified or forked interactive AGPL-covered SecPal works: `Based on SecPal`
- Preferred but not mandatory fuller notice: `Powered by SecPal - A guard's best friend`
- Preferred/requested but not mandatory: include or link to `https://secpal.app`

The tagline and website link are requests, not license conditions. The enforceable license conditions are the preservation of the appropriate SecPal attribution notice and the no-endorsement / no-misrepresentation rules in the approved addendum text.

Implementation notes:

- Modified versions must not use `Powered by SecPal` in a way that suggests they are the original SecPal release or endorsed by the SecPal project maintainers.
- The attribution terms do not require a specific footer layout, logo, visual design, or exact placement.
- Public footer formatting guidance remains in [`docs/brand/footer-wording.md`](./brand/footer-wording.md) and [`docs/brand/licensing-wording.md`](./brand/licensing-wording.md).

## CLA And Governance Alignment

- The CLA is a contributor license agreement, not a copyright assignment.
- Contributors retain copyright in their own work.
- Contributors grant SecPal, acting through the Project Maintainer, the rights needed to distribute contributions under the AGPL and to grant commercial licenses.
- If SecPal later forms or designates a successor legal entity, SecPal governance documentation must identify that successor clearly before repository headers or contributor-facing legal text are updated to reflect it.

See [`CLA.md`](../CLA.md) for the operative contributor agreement text and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for day-to-day REUSE guidance.

## Implementation Tracking

Repository follow-up issues for this policy:

- `api`: [SecPal/api#1226](https://github.com/SecPal/api/issues/1226)
- `frontend`: [SecPal/frontend#1323](https://github.com/SecPal/frontend/issues/1323)
- `android`: [SecPal/android#313](https://github.com/SecPal/android/issues/313)
