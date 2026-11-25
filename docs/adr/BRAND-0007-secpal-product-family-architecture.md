<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# BRAND-0007: SecPal Product Family Architecture

## Status

**Accepted**

## Date

2026-09-20

## Deciders

SecPal maintainers under the current human product decision recorded in #989

## Context

The organization needs one hierarchy for SecPal, SecPal Assure, and SecPal
Visit, with separate evidence for implementation and availability claims.

The organization-level audience has also broadened within a bounded category:
SecPal remains for security and security-adjacent processes, but a customer need
not be legally classified as a security company. The main SecPal product keeps
its direct professional-security-operations audience.

## Decision

The organization, company, and brand are `SecPal`.

The umbrella is the `SecPal product family`, or a semantically equivalent
surface-appropriate phrase. `SecPal Suite` is not the formal family name.

The current product family is:

- `SecPal`, the main product for professional security operations;
- `SecPal Assure`, a specialist product identity; and
- `SecPal Visit`, a specialist product identity.

The deliberate organization/product naming asymmetry is accepted. The main
product remains `SecPal`; no suffix is introduced merely to distinguish it from
the organization.

Use the full specialist names where the family relationship is not already
clear. Nearby references may use `Assure` and `Visit` only where the SecPal
relationship is unambiguous. Do not invent abbreviations.

SecPal Assure and SecPal Visit may be capable of standalone or integrated
operation. Standalone capability does not make either an independent brand
outside the SecPal family. Product naming, strategic identity, intended
direction, accepted architecture, implementation, availability, deployment,
and production qualification are separate claims. This ADR establishes the
approved names, strategic identities, intended family direction, and accepted
brand architecture. It does not establish implementation, availability,
deployment, or production qualification; current evidence governed by #763 is
required for those claims.

Central brand authority owns the family hierarchy, exact public names, allowed
short references, slogan approval, and shared presentation rules. Owning
product repositories, where they exist, own runtime configuration, code,
screenshots, icons, distributable assets, implementation detail, and evidence
of current status. A product identity does not require or imply a repository
with the same name, and repository topology does not create a product brand.

## Consequences

### Positive

- One current authority names the organization, family, main product, and
  specialist products without artificial naming suffixes.
- Standalone specialist-product direction is separated from independent brand
  identity and from implementation or availability claims.
- Central rules and product-repository responsibilities remain distinct.

### Negative

- Existing public and repository surfaces need separately owned reconciliation.
- The same `SecPal` name for organization and main product requires context in
  some copy.
- Approved specialist names cannot be used as evidence that products or assets
  exist.

## Alternatives Considered

1. **Add a suffix to the main product**
   - Rejected: the human product decision deliberately keeps the main product
     named `SecPal`.
2. **Formalize `SecPal Suite`**
   - Rejected: `SecPal product family` is the approved umbrella semantics.
3. **Give standalone specialist products independent brands**
   - Rejected: standalone capability does not change SecPal-family identity.

## Related

- [Product and Public Positioning Contract](../product-positioning.md)
- [Brand Architecture](../brand/brand-architecture.md)
- [Naming](../brand/naming.md)
- [Public Status Semantics](../public-status-semantics.md)
- [Issue #989](https://github.com/SecPal/.github/issues/989)
- [Status-semantics issue #763](https://github.com/SecPal/.github/issues/763)
