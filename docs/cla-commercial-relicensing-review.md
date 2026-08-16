<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# CLA And Commercial Relicensing Review

**Decision date:** 2026-08-16

**Tracking:** [SecPal/.github#651](https://github.com/SecPal/.github/issues/651), Gate 01 of [SecPal/.github#649](https://github.com/SecPal/.github/issues/649)

## Decision

**Targeted governance update required; no CLA text change required.** The existing individual and corporate contributor grants already cover distribution under plain `AGPL-3.0-or-later` and the grant of commercial licenses. Removing `LicenseRef-SecPal-Attribution` from SecPal's public outbound license expression therefore does not change the contributor-rights model or require contributors to grant additional rights.

The CLA already defines the recipient role but relies on public governance to identify its current holder. [`GOVERNANCE.md`](../GOVERNANCE.md) now makes that designation explicit and defines a succession process without amending the contributor grant.

This decision is limited to the planned outbound-license simplification. It does not approve a copyright assignment, add an attribution obligation, change product branding, or migrate repository SPDX metadata.

## Basis

The operative terms in [`CLA.md`](../CLA.md) establish the same rights model for individual and corporate contributors:

- The agreement-wide Purpose confirms that contributors retain full copyright ownership. The individual agreement also expressly reserves all right, title, and interest except for the license granted to SecPal and downstream recipients.
- Section 2 grants a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license. The grant includes reproduction, derivative works, public display and performance, sublicensing, and distribution.
- Section 2 expressly authorizes distribution under `AGPL-3.0-or-later`.
- Section 2 separately and expressly authorizes SecPal, acting through the Project Maintainer as the CLA rights recipient, to grant commercial licenses for contributions.
- The patent grants and contributor representations do not depend on the outbound attribution addendum and remain unchanged.

The grant is a license, not an assignment. Its express non-exclusive character and the reservation of contributor ownership rule out converting contributor copyright to SecPal ownership through this migration.

Plain `AGPL-3.0-or-later` is already named in the CLA. The broader rights to sublicense and distribute, together with the separate express commercial-license authorization, do not depend on an outbound additional term. Removing that additional term narrows the conditions imposed on public recipients; it does not require a broader inbound grant from contributors.

The current [SecPal attribution terms](../LICENSES/LicenseRef-SecPal-Attribution.txt) identify themselves as additional terms under AGPL sections 7(b) and 7(c). [AGPL section 7](https://www.gnu.org/licenses/agpl-3.0#section7) separately permits specified notice, attribution, origin, and modification-marking terms. That structure confirms that the addendum supplements the AGPL outbound terms rather than defining the CLA's inbound contributor grant.

## Rights Recipient And Administration

The defined terms in [`CLA.md`](../CLA.md), [`licensing-policy.md`](licensing-policy.md), and [`GOVERNANCE.md`](../GOVERNANCE.md) are aligned:

- `SecPal` is the open source project maintained by the Project Maintainer.
- `Project Maintainer` is the person or legal entity designated in public SecPal governance documentation to accept contributions, administer contributor agreements, and grant commercial licenses, including a legal successor or assignee of those rights. The current designee is the individual represented by GitHub account `@aroviqen`, GitHub user ID `266326653`.
- `CLA rights recipient` is SecPal acting through the Project Maintainer until a successor legal entity is publicly designated in governance documentation.

This designation remains coherent with the current administration paths: [`CLA_SETUP.md`](../.github/CLA_SETUP.md) links the organization-wide CLA service to the canonical CLA, and `legal@secpal.app` is the contact in the CLA for manual signatures, corporate-contributor changes, and legal questions. The governance record makes clear that changing account, team, repository, or email control does not transfer CLA rights. A later succession requires a legal assignment or other lawful succession and a public governance update before the successor is represented as the CLA rights recipient.

## Attribution Dependency Review

`CLA.md` contains no reference to `LicenseRef-SecPal-Attribution` and no clause that conditions the copyright or patent grants on that addendum. No CLA clause needs to be removed or amended for the outbound simplification.

The active attribution-addendum references reviewed outside the CLA have these effects:

- [`licensing-policy.md`](licensing-policy.md) currently defines the outbound SPDX and attribution policy. Updating those sections is Gate 02 work; its CLA-alignment section already describes the non-assignment, retained-copyright, AGPL-distribution, commercial-relicensing, and succession model correctly.
- [`README.md`](../README.md) and [`CONTRIBUTING.md`](../CONTRIBUTING.md) contain outbound licensing and REUSE guidance that refers to the addendum. Those references do not define or limit the inbound CLA grant and are to be aligned by the ordered central-policy migration.
- [`legal-compliance.md`](legal-compliance.md) does not define contributor grants or commercial-relicensing rights. It retains the broader requirement for external legal review before production launch.
- [`CLA_SETUP.md`](../.github/CLA_SETUP.md) is operational guidance. It points to the canonical `CLA.md`, records that changing the CLA requires re-signing, and does not encode the attribution addendum.

Because the operative CLA is unchanged, this decision does not itself trigger CLA Assistant re-signing. Later outbound SPDX or policy changes must not be represented as changes to already granted contributor rights.

## Rights-Model Invariants For Later Gates

Later migration work may rely on these conclusions:

- Contributors retain copyright in their contributions.
- SecPal receives a non-exclusive license, not a copyright assignment.
- The existing grant covers distribution under plain `AGPL-3.0-or-later`.
- The existing grant separately covers commercial licensing.
- Removing the public attribution addendum neither expands nor reduces contributor grants.
- The Project Maintainer remains the administrator and CLA rights recipient for SecPal, subject to the documented public-succession mechanism.
- The current rights recipient is explicitly designated in public governance; administrative account or team changes alone cannot transfer those rights.
- No new attribution, branding, copyright-assignment, or contributor re-signing requirement follows from this decision.

This is a governance and document-consistency decision for the migration. The external-counsel review tracked in [`legal-compliance.md`](legal-compliance.md) remains the path for a formal legal opinion.
