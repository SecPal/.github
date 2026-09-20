<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Product and Public Positioning Contract

## Status and Authority

Canonical. This document is the single organization-wide authority for what
SecPal product descriptions mean and which claims fall outside the accepted
public position. SecPal maintainers are its decision authority.

This is a product-positioning contract, not an architecture decision record and
not mandatory marketing copy. Accepted ADRs remain authoritative for
architecture, technology, security, legal, and process decisions. The accepted
brand authority remains authoritative for brand hierarchy, names, slogans,
typography, footer wording, and other presentation mechanics.

Short and long descriptions MAY be adapted to their surface and audience. They
MUST remain semantically consistent with this contract and MUST distinguish
intended direction from current implementation. No paragraph in this document
is universal text that every public surface must copy verbatim.

## Stable Product Principles

The principles in this section define SecPal's durable public position. They do
not assert that every intended product or capability is implemented.

### Organization and Product-Family Positioning

SecPal develops software for security and security-adjacent processes. Its
customers do not have to be legally classified as security companies. A German
surface may express the same guardrail as:

> SecPal entwickelt Software für Sicherheits- und sicherheitsnahe Prozesse.
> Unsere Kunden müssen deshalb nicht zwingend Sicherheitsunternehmen sein.

This is a semantic positioning boundary, not required marketing copy. SecPal
remains anchored in security and security-adjacent processes; it is not a
generic ERP, HR, visitor-management, document-management, or compliance
platform. Generic business capabilities may be integrated where useful without
changing that identity.

Current SecPal domain knowledge is strongly grounded in German security
operations. German private-security requirements remain important to the main
product and current domain modelling. That current focus is not a permanent
organization-level customer eligibility rule, and it does not establish
suitability or compliance for arbitrary foreign regulatory markets.

### Product Family and Main-Product Audience

The organization, company, and brand are named `SecPal`. The umbrella is the
`SecPal product family`; `SecPal Suite` is not its formal name. The main product
is also named `SecPal`. No suffix such as `Core`, `Operations`, `Guard`, or
`Platform` is added merely to distinguish it from the organization.

The main SecPal product is directly designed for professional security
operations, including private security services, in-house security, plant
protection (`Werkschutz`), corporate security (`Unternehmensschutz`), and
comparable professional security organizations. The broader family boundary
does not generalize this main-product audience to all companies.

The approved specialist-product identities are `SecPal Assure` and `SecPal
Visit`. They may be intended to operate standalone or integrated with SecPal
and may serve a broader security-adjacent audience than the main product. Where
the SecPal relationship is already unambiguous, nearby references may use
`Assure` and `Visit`.

GuardGuide is retired from the current SecPal product strategy and active brand
architecture. `GuardGuide`, `GuardGuide by SecPal`, `VisitGuide`, and
`VisitGuard` are not current product brands. Historical GuardGuide commits,
issues, ADRs, and changelog entries remain truthful historical evidence.

### Integrated-System Direction

The main SecPal product is intended as an integrated system spanning
administrative and operational work where those domains meaningfully belong
together. It is not defined by any one current or future capability, such as
guard tours or OWKS, scheduling, guard book, employee or HR management, working
time, contracts, instructions, reporting, or customer and site management.
These are illustrative domains that may belong in SecPal; the list is neither a
promised feature inventory nor a claim of present implementation.

Specialist products may operate independently or integrate with the main
product. Standalone capability does not create an independent brand outside the
SecPal product family and does not prove that a runtime integration exists.

### Product Boundary

SecPal should own domain-specific workflows, data relationships, and
integrations where unified ownership creates meaningful value for security or
security-adjacent processes. The family does not need to reproduce arbitrary
general-purpose enterprise software merely because a customer uses it. Generic
business capabilities may be integrated instead of rebuilt when SecPal-specific
ownership would not meaningfully improve the relevant workflow. Future boundary
cases remain product decisions rather than being pre-decided here.

### Intended User Value

SecPal's direction goes beyond digitising existing paperwork. It is intended to:

- safely reduce repetitive work that software can perform;
- reduce avoidable duplicate entry and manual transfer between disconnected
  processes;
- connect information and workflows that meaningfully belong together;
- make work easier, clearer, more reliable, and safer for the people doing it;
  and
- retain necessary domain complexity inside the system without unnecessarily
  exposing that complexity to users.

Necessary complexity may live in the system; it should not unnecessarily live
with the user. This is a product-design principle, not a legal, regulatory, or
compliance guarantee.

Professional security work in Germany can involve substantial interaction
between operational work, administration, documentation, employment,
qualifications, scheduling, working time, authorization, customer and site
requirements, and other domain constraints. That context explains the value of
an integrated main product. It does not claim that SecPal currently models
every applicable requirement, or models any requirement correctly merely
because it is named.

### Foundation Before Feature Volume

SecPal deliberately prefers durable technical and domain foundations over
accumulating feature volume on structures already known to be wrong. Accepted
architecture can evidence this project direction, but acceptance of an ADR does
not prove that its target architecture has been implemented.

### Honest Pre-1.0 Evolution

SecPal is under active development and remains pre-1.0. Architecture, domain
modelling, and implementation may change materially during this period. This is
a stable statement about project maturity, not an apology and not permission to
present intent as delivered capability.

### Open Source and Independent Operation

Open Source is fundamental to SecPal:

- SecPal public product software is open source and inspectable.
- Independent operation and self-hosting are intentional properties of the
  public project.
- Portable technical contracts required for independent operation remain
  public under
  [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md).
- Public development makes implementation and technical decisions inspectable
  rather than asking readers to rely on opaque marketing assertions.
- External contribution and independent improvement are possible.

These principles do not establish that SecPal is community-driven, has a large
community, or has broad adoption. They do not imply that every repository or
internal project in the SecPal organization must be public.

ADR-023 preserves the distinction: private managed customer and fleet
inventory, commercial policy, customer-specific orchestration, and other
accepted managed-operations responsibilities may remain separate. Those private
responsibilities do not make SecPal public product software non-open-source,
and private managed operations MUST NOT become a hidden technical dependency
for independent operation. Licensing and Open Source wording remain subject to
the [SecPal Licensing Policy](licensing-policy.md) and existing repository and
file-specific license authorities.

## Product Identity and Status Semantics

Public positioning MUST keep these independent dimensions distinct:

- an approved name or strategic product identity;
- intended product direction;
- architecture accepted through the ADR process;
- current implementation supported by source evidence;
- availability to users;
- deployment in an environment; and
- production qualification or operation.

Naming `SecPal Assure` or `SecPal Visit` establishes approved strategic product
identity and direction only. It does not prove that either product is
implemented, released, generally available, deployed, integrated, or
production-ready. Standalone or integrated operation describes permitted
product direction, not current runtime evidence.

Likewise, GuardGuide's removal from current brand authority does not erase its
historical implementation or delivery evidence. Historical evidence does not
restore GuardGuide as a current product identity.

The detailed vocabulary, admissible evidence, and downgrade rules are defined
by the [Public Status Semantics](public-status-semantics.md) established under
[#763](https://github.com/SecPal/.github/issues/763). Public authors MUST use
the strongest claim supported by current evidence and MUST NOT promote one
dimension into another.

## Mutable Decisions

The stable principles do not freeze the exact feature or module set, future
product set, implementation technology not otherwise fixed by an accepted ADR,
current architecture details, prioritization, roadmap order, release timing,
repository topology, or future international expansion. These examples are not
exhaustive.

Mutable decisions MUST remain free to evolve through their owning product,
domain, architecture, implementation, and planning processes. Public wording
MUST NOT convert them into permanent positioning commitments or guaranteed
delivery.

## Relationship to Existing Authorities

This contract delegates rather than duplicates established authority:

- [BRAND-0007](adr/BRAND-0007-secpal-product-family-architecture.md) and the
  active [Brand Architecture](brand/brand-architecture.md) own the current
  SecPal product-family hierarchy. BRAND-0007 supersedes BRAND-0001 for current
  product identity while preserving BRAND-0001 as historical evidence.
- [Naming](brand/naming.md) owns exact public names and capitalization.
- [Slogans](brand/slogans.md) owns exact slogan and lockup presentation. The
  official SecPal slogan remains exactly `A guard's best friend`, and the
  approved lockup remains exactly `SecPal – A guard's best friend`.
- The [SecPal Licensing Policy](licensing-policy.md) and
  [Licensing Wording](brand/licensing-wording.md) own licensing and
  human-readable Open Source wording within their respective scopes.
- [ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) remains the
  accepted tenant, identity, employee, and access boundary. Newer unresolved
  employee, working-time, absence, or related ideas do not become accepted
  architecture through this positioning contract.
- [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md)
  remains the accepted public-self-hosting and private-managed-operations
  boundary.
- The ADR index currently keeps
  [ADR-001](adr/20251027-event-sourcing-for-guard-book.md),
  [ADR-002](adr/20251027-opentimestamp-for-audit-trail.md), and
  [ADR-003](adr/20251027-offline-first-architecture.md) Proposed and
  non-binding. Positioning language MUST NOT promote their unresolved decisions
  into accepted architecture or implemented capability.

References to any accepted ADR describe decision authority only. They MUST NOT
be represented as evidence that the accepted architecture is implemented,
deployed, production-ready, or operationally verified.

## Successor and Historical Positioning

This contract was originally established under completed
[#762](https://github.com/SecPal/.github/issues/762). The successor decision in
[#989](https://github.com/SecPal/.github/issues/989) refines #762 where the
current human product decision changed the organization-level audience,
product-family hierarchy, and GuardGuide status. Issue #762 remains historical
evidence and its still-valid principles continue here.

Completed [#340](https://github.com/SecPal/.github/issues/340) and
[#344](https://github.com/SecPal/.github/issues/344) also remain preserved
historical positioning evidence. Their rollout and evidence are not erased.

The sentence `Everything the day-to-day operation needs — in one system that
just works.` remains superseded as active organization-wide positioning. Its
early aspiration is understandable in historical context, but current use can
imply feature completeness and maturity that SecPal does not claim.

## Prohibited Public-Positioning Overclaims

Public descriptions MUST NOT present unsupported claims as fact, including:

- feature, product, or domain completeness;
- implementation or availability inferred only from an approved product name;
- production readiness or unsupported maturity;
- legal or regulatory compliance guarantees;
- unsupported security assurance, including `enterprise-grade`,
  `military-grade`, `bank-grade`, `unhackable`, `compliance-ready`, or
  `zero-trust platform`;
- unsupported community size, contribution scale, or adoption;
- suitability for foreign markets that have not been evaluated; or
- fixed roadmap order, release dates, delivery certainty, or international
  expansion.

Specific factual claims may be made only when supported by the authority and
evidence appropriate to that claim.

## Scope Boundary

This contract defines semantic consistency for future public descriptions. It
does not itself rewrite a repository README, organization profile, website,
roadmap, deployment or API documentation, or product copy. It changes no
runtime behavior, creates no repositories or runtime products, decides no
unresolved architecture, establishes no fixed feature sequence, and creates no
compliance or legal guarantee. Applying it to individual surfaces is separately
owned follow-up work.
