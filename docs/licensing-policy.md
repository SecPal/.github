<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Licensing Policy

This document is the authoritative SecPal policy for contributor licensing and SPDX/REUSE metadata across shared repositories such as `api`, `frontend`, and `android`.

## Defined Terms

- **SecPal** means the SecPal open source project maintained by the Project Maintainer.
- **Project Maintainer** means the person or legal entity designated in SecPal governance documentation as responsible for accepting contributions, administering contributor agreements, and granting commercial licenses for the SecPal project, including any legal successor or entity to which those rights are assigned.
- **CLA rights recipient** means SecPal acting through the Project Maintainer unless and until SecPal publicly designates a successor legal entity in its governance documentation.

These definitions keep the CLA model as a license grant rather than a copyright assignment: contributors retain copyright ownership and grant SecPal the rights needed for AGPL distribution and commercial relicensing.

[`GOVERNANCE.md`](../GOVERNANCE.md) records the current Project Maintainer, through whom SecPal acts as the CLA rights recipient, and the required process for a later lawful succession. Administrative account, team, repository, or email control does not by itself replace that designation or transfer CLA rights.

## Standard SPDX Copyright Policy

Use project-based copyright notices for SecPal-owned material:

```text
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
```

For files first published in 2026:

```text
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
```

Rules:

- Use `SecPal Contributors` for project-owned source code, policy documents, and other repository-owned material.
- Use the plain SPDX expression `AGPL-3.0-or-later` for SecPal-owned material intentionally covered by the AGPL. Do not add a project-specific attribution term to that expression.
- Do not use `SecPal` alone as the copyright holder for project-owned code unless SecPal later publishes a clear legal entity or other documented rights holder for that specific use.
- Keep third-party notices separate. Do not replace upstream names, bundled notices, or vendor copyright statements with `SecPal Contributors`.
- Do not switch third-party or externally-authored notices to `SecPal Contributors` just for consistency.

## Active License Model

SecPal-owned material intentionally covered by the AGPL is licensed under plain `AGPL-3.0-or-later`. The former SecPal attribution addendum is retired and is not part of the active outbound licensing model.

Rules:

- Apply `AGPL-3.0-or-later` only where the material is intentionally AGPL-covered; do not convert deliberately different licenses merely for consistency.
- Preserve `CC0-1.0`, `MIT`, `Apache-2.0`, third-party licenses, generated-file licenses, and unrelated custom license references where they intentionally apply.
- Keep per-file SPDX metadata and repository-level REUSE annotations accurate when a repository contains material under multiple licenses.
- Review new third-party or custom-license material for compatibility and document any required license text without expanding the SecPal-owned AGPL expression.

## Third-Party And Tailwind Rules

- Third-party notices must remain under their original licensing and attribution terms.
- Keep third-party REUSE metadata separate from SecPal-owned metadata.
- Do not add Tailwind-specific licensing terms to `api`, `frontend`, or `android` unless Tailwind-derived material is actually present in that repository.
- If Tailwind-derived material is present, keep that handling repository-specific and separate from SecPal-owned AGPL metadata.

## Branding Is Separate From Licensing

Official SecPal branding is separate from the AGPL licensing obligations. The project continues to use `Powered by SecPal – A guard's best friend` on official SecPal product surfaces where the brand documentation requires it, but that official presentation standard is not an additional license condition.

Official-project developers follow [`docs/brand/footer-wording.md`](./brand/footer-wording.md), [`docs/brand/licensing-wording.md`](./brand/licensing-wording.md), and [`docs/brand/slogans.md`](./brand/slogans.md) for brand presentation. Those documents govern SecPal-maintained product surfaces; they do not alter the permissions or obligations of `AGPL-3.0-or-later` or create fork-specific licensing instructions.

## CLA And Governance Alignment

- The CLA is a contributor license agreement, not a copyright assignment.
- Contributors retain copyright in their own work.
- Contributors grant SecPal, acting through the Project Maintainer, the rights needed to distribute contributions under the AGPL and to grant commercial licenses.
- The current Project Maintainer, through whom SecPal acts as the CLA rights recipient, is designated in [`GOVERNANCE.md`](../GOVERNANCE.md).
- If SecPal later forms or designates a successor legal entity, a legal assignment or other lawful succession must occur and SecPal governance documentation must identify that successor clearly before repository headers or contributor-facing legal text are updated to reflect it.

See [`CLA.md`](../CLA.md) for the operative contributor agreement text and [`CONTRIBUTING.md`](../CONTRIBUTING.md) for day-to-day REUSE guidance.

The Gate 01 review in [`cla-commercial-relicensing-review.md`](cla-commercial-relicensing-review.md) records why the existing CLA grant already covers distribution under plain `AGPL-3.0-or-later` and commercial relicensing without changing contributor rights or the CLA text.

## Implementation Tracking

Repository follow-up issues for this policy:

- `api`: [SecPal/api#1425](https://github.com/SecPal/api/issues/1425)
- `frontend`: [SecPal/frontend#1680](https://github.com/SecPal/frontend/issues/1680)
- `android`: [SecPal/android#593](https://github.com/SecPal/android/issues/593)
- `deployment`: [SecPal/deployment#45](https://github.com/SecPal/deployment/issues/45)
