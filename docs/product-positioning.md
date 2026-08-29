<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Product and Public Positioning Contract

## Status and authority

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
is a universal text that every public surface must copy verbatim.

## Stable product principles

The principles in this section define SecPal's durable public position. They do
not assert that every intended domain or capability is already implemented.

### Identity, audience, and category

SecPal is being built for private security services operating in Germany. This
describes the operating and domain context, not the nationality or ownership of
the companies that use SecPal. The focus is deliberate because current project
knowledge and domain modelling concern the German private-security environment.
Suitability for security markets outside Germany has not been established, and
international expansion remains undecided.

The intended product-category semantics are:

- German: **Betriebs- und Einsatzsoftware für private Sicherheitsdienste in
  Deutschland**
- English: **integrated operations software for private security services in
  Germany**

In this context, German `Einsatzsoftware` does not translate to English
`deployment software`, which could be confused with software or infrastructure
deployment. The English category also MUST NOT be narrowed to workforce, human
resources, or scheduling software.

Open Source is a separate stable characteristic of SecPal, not a decorative
modifier whose meaning depends on one canonical marketing sentence. A public
surface MAY combine the category and Open Source in surface-appropriate prose
when it preserves both meanings and describes intended direction honestly.

### Integrated-system direction

SecPal is intended as an integrated system spanning administrative and
operational work where those domains meaningfully belong together. It is not
defined by any one current or future capability, such as guard tours or OWKS,
scheduling, guard book, employee or HR management, working time, contracts,
instructions, reporting, or customer and site management. These are
illustrative domains that may belong in SecPal; the list is neither a promised
feature inventory nor a claim of present implementation.

### Product boundary

SecPal should own domain-specific workflows, data relationships, and
integrations where unified ownership creates meaningful operational value for
private security services. SecPal does not need to reproduce arbitrary
general-purpose enterprise software merely because a security company uses it.
Generic business capabilities may be integrated instead of rebuilt when
SecPal-specific ownership would not meaningfully improve the security-service
workflow. Future boundary cases remain product decisions rather than being
pre-decided here.

### Intended user value

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

Private security work in Germany can involve substantial interaction between
operational work, administration, documentation, employment, qualifications,
scheduling, working time, authorisation, customer and site requirements, and
other domain constraints. That context explains the value of an integrated
system. It does not claim that SecPal currently models every applicable
requirement, or models any requirement correctly merely because it is named.

### Foundation before feature volume

SecPal deliberately prefers durable technical and domain foundations over
accumulating feature volume on structures already known to be wrong. Accepted
architecture can evidence this project direction, but acceptance of an ADR does
not prove that its target architecture has been implemented.

### Honest pre-1.0 evolution

SecPal is under active development and remains pre-1.0. Architecture, domain
modelling, and implementation may change materially during this period. This is
a stable statement about project maturity, not an apology and not permission to
present intent as delivered capability.

Public positioning MUST keep these distinct:

- the stable principles in this contract;
- architecture accepted through the ADR process;
- current implementation supported by current evidence;
- mutable product and domain decisions;
- prioritisation; and
- roadmap or exploratory work.

The detailed vocabulary and evidence rules for public project-state claims are
outside this contract. This contract establishes only the positioning-level
distinction required to prevent direction or accepted architecture from being
presented as implementation fact.

### Open Source

Open Source is fundamental to SecPal:

- SecPal itself is open source, and its software is inspectable.
- Independent operation and self-hosting are intentional properties of the
  public project.
- Portable technical contracts required for independent operation remain
  public under
  [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md).
- Public development makes implementation and technical decisions inspectable
  rather than asking readers to rely on opaque marketing assertions.
- External contribution and independent improvement are possible.

These principles do not establish that SecPal is community-driven, has a large
community, or has broad adoption. They also do not imply that every repository
or internal project in the SecPal organization must be public.

ADR-023 preserves the distinction: private managed customer and fleet
inventory, commercial policy, customer-specific orchestration, and other
accepted managed-operations responsibilities may remain separate. Those private
responsibilities do not make SecPal itself non-open-source, and private managed
operations MUST NOT become a hidden technical dependency for independent
operation. Licensing and Open Source wording remain subject to the
[SecPal Licensing Policy](licensing-policy.md) and the existing repository and
file-specific license authorities.

## Mutable decisions

The stable principles do not freeze the exact feature or module set, feature
names, product boundaries in every future case, implementation technology not
otherwise fixed by an accepted ADR, current architecture details,
prioritisation, roadmap order, release timing, or future international
expansion. These examples are not exhaustive.

Mutable decisions MUST remain free to evolve through their owning product,
domain, architecture, implementation, and planning processes. Public wording
MUST NOT convert them into permanent positioning commitments or guaranteed
delivery.

## Relationship to existing authorities

This contract delegates rather than duplicates established authority:

- [BRAND-0001](adr/BRAND-0001-brand-architecture.md) and the accepted
  [Brand Architecture](brand/brand-architecture.md) define SecPal as the
  platform and product family and `GuardGuide by SecPal` as a standalone product
  in that family. The existing first-mention and short-name rules remain
  authoritative; this contract neither reopens nor alters that hierarchy.
- [Naming](brand/naming.md) owns exact public names and capitalization.
- [Slogans](brand/slogans.md) owns exact slogan and lockup presentation. The
  official SecPal slogan remains exactly `A guard's best friend`, and the
  approved brand-plus-slogan lockup remains exactly
  `SecPal – A guard's best friend`. Capitalization, apostrophe, separator,
  spacing, terminal punctuation, translation, and variant rules are defined
  there and MUST NOT be locally redefined.
- The [SecPal Licensing Policy](licensing-policy.md) and
  [Licensing Wording](brand/licensing-wording.md) own licensing and
  human-readable Open Source wording within their respective scopes.
- [ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) remains the
  accepted tenant, identity, employee, and access boundary. Newer unresolved
  `Employee`, `EmploymentPeriod`, `EmploymentTermsVersion`, working-time,
  absence, or related ideas do not become accepted architecture through this
  positioning contract.
- [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md)
  remains the accepted public-self-hosting and private-managed-operations
  boundary.
- The ADR index keeps
  [ADR-001](adr/20251027-event-sourcing-for-guard-book.md),
  [ADR-002](adr/20251027-opentimestamp-for-audit-trail.md), and
  [ADR-003](adr/20251027-offline-first-architecture.md) Proposed and
  non-binding. Positioning language MUST NOT promote their Guard Book,
  timestamping, or offline decisions, or any other unresolved domain idea, into
  accepted architecture or implemented capability.

References to any accepted ADR describe decision authority only. They MUST NOT
be represented as evidence that the accepted architecture is implemented,
deployed, production-ready, or operationally verified.

## Historical positioning

Completed [#340](https://github.com/SecPal/.github/issues/340) and
[#344](https://github.com/SecPal/.github/issues/344) remain preserved historical
positioning evidence. Their rollout and evidence are not invalidated or erased.

The sentence `Everything the day-to-day operation needs — in one system that
just works.` is superseded as active organization-wide positioning wording. Its
early aspiration remains understandable in historical context, but current use
can imply feature completeness and maturity that SecPal does not claim. This
contract succeeds that wording with durable principles and semantic boundaries,
not another immutable completeness-oriented marketing sentence.

## Prohibited public-positioning overclaims

Public descriptions MUST NOT present unsupported claims as fact, including:

- feature or domain completeness;
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
evidence appropriate to that claim. This section defines positioning boundaries;
it does not create the detailed public status taxonomy.

## Scope boundary

This contract defines semantic consistency for future public descriptions. It
does not itself rewrite a repository README, organization profile, website,
roadmap, deployment or API documentation, or product copy. It changes no
runtime behavior, decides no unresolved architecture, establishes no fixed
feature sequence, and creates no compliance or legal guarantee. Applying it to
individual surfaces is separately owned follow-up work.
