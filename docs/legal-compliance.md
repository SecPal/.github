<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Legal & Regulatory Compliance

Use the applicable legal sources and the customer's actual workflow when
assessing obligations or making compliance claims. Record the source version
and review date for legal and tariff rules used by the product.
[ADR-025](adr/20261002-employment-time-absence-compensation-adr025.md) defines
that requirement for working time, absence, leave, and compensation.

## GDPR (General Data Protection Regulation)

Assess the controller and processor roles for each workflow. Identify the
purpose, legal basis, access and retention for each data category. Keep records
of processing where required and provide an applicable processor agreement.
Support access, rectification, erasure, restriction, notification to recipients,
portability and objection where the respective conditions apply.

For an erasure request, check applicable retention obligations and legal holds
per record category. Retain the required evidence and minimize the retained
personal data. Assess notification and documentation obligations for a breach
under Articles 33 and 34 and identify the competent supervisory authority.

[GDPR official text](https://eur-lex.europa.eu/eli/reg/2016/679/oj)

[ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) defines tenant
integrity, scope, access, encryption, minimization and retention. Employee
records and properly retained evidence survive deletion of a linked global
User. Historical ended memberships neither block User deletion nor
cascade-delete with the User. Global User email uses an encrypted value and a
keyed index. [ADR-015](adr/20260720-global-identity-key-security-adr015.md)
defines the separate Global Identity Key boundary.
[ADR-026](adr/20261002-client-trust-offline-recovery-adr026.md) defines offline
authorization, revocation and recovery.

## BewachV (Bewachungsverordnung)

The security service operator owns registration of guard and supervisory
personnel, service instructions, recordkeeping, and retention. Section 21
specifies the contract and personnel records and supporting documents, their
retention periods, and the events from which those periods run. Derive
retention by record category and verified legal basis.
[GewO § 34a](https://www.gesetze-im-internet.de/gewo/__34a.html),
[BewachV §§ 16–17 and 21](https://www.gesetze-im-internet.de/bewachv_2019/)

Product requirements include traceable operational records, auditable
corrections, and authorized presentation of relevant evidence to the
competent authority. Where a workflow requires evidence of chronology and
integrity, document which records are covered and how to verify them.
[ADR-010](adr/20251221-activity-logging-audit-trail-strategy.md) covers the
application audit trail. Audit evidence alone does not qualify the Guard Book
or any retention, archival, or export procedure.

The tenant and access decision retains the BWR identifiers, status, reporting
dates, authority decisions and authorized manual process for evaluation.
[ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) calls for
removing the BWR file export without a replacement endpoint.

## DIN 77200 and ISO 9001

Where a customer requires conformance, map traceable service documentation,
incident handling, process evidence and audit access to the applicable
standard and service scope. Assess certification separately for the
organization and scope to which it applies.
[DIN 77200-1](https://www.dinmedia.de/de/norm/din-77200-1/348823032),
[ISO 9001:2015](https://www.iso.org/standard/62085.html)

## NIS2

Assess applicability under the relevant national transposition using the
actual service, entity, and applicable criteria. Where applicable, evaluate
incident reporting, security risk management, supply-chain security, and
training. [NIS2 Directive](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

## Related

- [CLA and commercial relicensing review](cla-commercial-relicensing-review.md)
- [Product requirements](feature-requirements.md)
