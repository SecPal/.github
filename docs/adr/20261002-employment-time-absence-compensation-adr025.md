<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-025: Employment, Working Time, Absence, and Compensation Authorities

**Status:** Accepted

**Date:** 2026-10-02

**Decision authority:** SecPal Product and Domain Owner

**Partially supersedes:** [ADR-014](20260720-tenant-identity-access-model-adr014.md)

**Decision provenance:** This ADR records the September 2026 product/domain
rebaseline explicitly authorized for acceptance under
[#841](https://github.com/SecPal/.github/issues/841). Its date is the architecture
record date. Acceptance establishes architecture authority, not implementation,
availability, migration completion, or legal compliance.

## Context

ADR-014 established the Tenant, global identity, Employee, and access baseline
on 2026-07-20. It required one authoritative contract projection on Employee,
transactional application of future changes to that projection, and left rehire
and several employment periods unresolved. The accepted product/domain decision
now requires a long-lived Employee, distinct employment periods, immutable
terms versions, and separate operational, accounting, and compensation truths.
Positioning or project-source prose cannot make that change authoritative.

This record accepts those boundaries together as one architecture contract. It
neither implements the model nor finalizes every scheduling, legal, tariff,
payroll, or user-interface detail.

## Relationship to ADR-014 and ADR-015

This ADR partially supersedes ADR-014 **only** where it:

- defines the Employee as the authoritative contract projection, including the
  binding-boundaries table, the Employee/contract section, the domain diagram
  and its explanation;
- applies future amendments by mutating that projection on their effective date;
- derives membership employment bases and lifecycle reevaluation from that
  projection, including the user-deletion diagram;
- rejects a separate employment-period concept or leaves rehire and several
  employment periods unresolved, including open detail decision 8; or
- repeats those assumptions in the API, Contracts, and test impact inventory.

Those decisions are replaced by Employee → EmploymentPeriod →
EmploymentTermsVersion and the time-dependent basis evaluation below. The
rejection of **overlapping employment periods for one Employee** remains: rehire
history does not authorize simultaneous employment contracts in that record.
All other ADR-014 decisions remain binding, including Tenant/TenantKey identity,
global User, TenantMembership, explicit access assignment, scope and validity,
tenant integrity, establishment history, encryption, retention, invitation,
active-context, and identity-deletion boundaries. The membership-state priority
and identity lifecycle locking remain unchanged; only the employment authority
they consume changes.

The new working-time, absence, leave, and compensation boundaries refine that
baseline. ADR-014 remains the owner of its retained identity/access/security
invariants; this ADR owns the replacement employment and added domain boundaries.
Its historical body and original decision date remain preserved. References to
its superseded projection are historical, including implementation inventories;
they are not a second current architecture authority.

[ADR-015](20260720-global-identity-key-security-adr015.md) continues to own Global
Identity Key security without modification or reopening.

## Binding decision

### Identity, employment, and authorization

`User != TenantMembership != Employee != Employment`.

Tenant remains exactly one legal entity/company. User is global authentication
identity. TenantMembership assigns that identity to a Tenant while a valid basis
exists. Employee is a long-lived personnel record belonging to exactly one
Tenant and surviving deletion of a linked User. Employment is the time-bounded
employment relationship represented by EmploymentPeriod; neither the Employee
record nor a membership is that relationship.

One Employee may have multiple **non-overlapping EmploymentPeriod** records,
including agreed future periods and ended periods across rehire history. Each
period belongs to that Employee and Tenant and has explicit start/end validity;
an open end does not permit overlap. An ended period remains history and never
creates a current employment basis. Rehire creates another period on the same
Employee rather than overwriting the ended period or creating a new global
identity. All domain references must preserve the same-Tenant integrity rules
of ADR-014.

Employment conditions are authoritative **immutable, effective-dated
EmploymentTermsVersion** records within an EmploymentPeriod. The applicable
version is resolved for the relevant instant or interval. Future versions do not
replace current conditions early. There must be one unambiguous applicable
terms version throughout a period's effective employment interval. Amendments
and corrections preserve prior versions and their effective dates, source
evidence, and recorded provenance; they cannot silently rewrite historical
calculations. A current-terms display or cache is a derived projection, never
an Employee-level contract authority. Resolution and correction mechanics,
physical storage, and exact fields remain implementation decisions.

Contract documents, amendments, and agreements remain separately retained legal
and documentary evidence. A terms version references its basis; it does not
replace the signed agreement or determine every legal dispute by itself.

Establishment assignment remains a separate time-dependent truth under
ADR-014: one current assignment during current employment, a schedulable
matching future assignment, non-overlap, and reproducible establishment history.
An assignment is neither an employment period nor terms, and creates no rights.
Onboarding and termination workflow/evidence also remain separate. Draft,
approval, signature, dispatch, receipt, notice expiry, and employment end do not
collapse into one period status. A draft termination does not establish a legal
end; an authoritative employment end must have its own validated basis.

Membership employment bases now derive from current/future EmploymentPeriod
validity and its authoritative terms/evidence, rather than mutable Employee
contract fields. Ending one period does not discard another future basis or a
valid Access Grant. Changes to periods, terms, and their effective boundaries
participate in ADR-014's centralized, transactional, Tenant-spanning lifecycle
evaluation and scheduled boundary evaluation. Historical periods alone do not
preserve membership or User identity.

Employment, establishment, position, management level, onboarding, termination,
and contract state grant **no automatic authorization**. Rights still require
an explicit TenantMembership Access Assignment with permission, scope, validity,
and revocation checks. Employment as a membership basis is not an access grant;
self-service and onboarding rights remain explicit.

### Contract, plan, actual work, credit, and settlement

`CONTRACT != PLAN != ACTUAL != CREDIT != COMPENSATION`.

These are separate authorities even when a calculation consumes several:

| Authority             | Meaning and boundary                                                                                     |
| --------------------- | -------------------------------------------------------------------------------------------------------- |
| Contractual target    | Work obligation derived from applicable employment terms and separately justified obligation adjustments |
| Plan/allocation       | Intended scheduling and allocation; a plan does not prove performance                                    |
| TimeCapture           | Capture evidence, with source and corrections; a capture alone does not settle accepted actual work      |
| Actual Work           | Work actually performed, represented through WorkSession / WorkSegment with traceable evidence           |
| Credited Time         | Time recognized under an applicable rule, including justified non-work credit; it is not fabricated work |
| WorkingTimeSettlement | A versioned assessment of target, actual, credit, variance, and applicable account rules                 |
| WorkingTimeAccount    | Immutable ledger postings and explicit reversals from justified settlement/account events                |
| Compensation          | A separate versioned monetary calculation with its own applicable inputs and rules                       |

WorkSession identifies a performed-work occurrence; WorkSegment preserves
relevant subdivisions such as activity, location, or rule-effective boundaries
where needed. Their detailed segmentation, approval, and Time Capture UX remain
open. Evidence correction must retain provenance rather than silently changing
what was accepted as actual work.

Actual Work must never be fabricated to satisfy contractual target, payroll,
absence, guarantee, credited-time, or account calculations. A planned shift is
not automatically actual work. A non-work credit may count under an identified
rule without becoming a performed session or segment.

Raw variance is the arithmetic difference for an explicitly defined comparison
basis and interval. Classified variance adds the rule-based reason and treatment;
a raw shortfall does not itself establish employee debt, overtime, payable time,
or a ledger posting. WorkingTimeSettlement records the input versions,
comparison basis, interval, classifications, and rule provenance used. Revisions
remain traceable to the settlement they replace.

WorkingTimeAccount balances are **ledger-derived**. Postings are immutable;
correction uses explicit linked reversals and replacement postings, preserving
origin and settlement provenance. A mutable balance field cannot be authority.
A cache may reproduce the ledger but cannot independently change it. Repeated
processing of the same accepted account event must not duplicate its effect.
Settlement does not itself establish compensation entitlement, and compensation
does not silently rewrite work or the working-time ledger.

### Absence, restriction, obligation, and scheduling privacy

`Absence != WorkRestriction != WorkObligationOverride != Leave != SchedulingPreference`.

- **AbsenceCase** records an absence occurrence, its interval, category, and
  necessary evidence/workflow. It does not by itself determine leave consumption,
  work credit, compensation, or every scheduling constraint.
- **WorkRestriction** expresses a constraint on permissible work or activities,
  with validity and a justified basis. A person may still be available for
  suitable work; restriction is not equivalent to absence.
- **WorkObligationOverride** records a separately justified, time-dependent
  adjustment to the work obligation. It changes the target under applicable
  rules, not actual work evidence, and does not automatically create credit.
- **Leave** has its own entitlement and consumption authority. A linked absence
  does not replace that authority or independently consume entitlement.
- **SchedulingPreference** expresses a preference such as wish-free. It is not
  vacation, absence, performed or credited work, or an automatic account posting.

These concepts may refer to one another when a justified rule requires it, but
must not be collapsed into one Employee status or generic absence flag. A
relationship does not authorize effects in another domain without that domain's
own rules and provenance.

Scheduling receives only the minimum availability/constraint information
necessary for allocation, such as the effective interval and permitted work.
HR or medical details and evidence remain behind their own explicit permissions,
scope, encryption, and retention boundaries. Availability must not require
exposing a diagnosis or complete personnel case to a scheduler.

### Leave entitlement and ledger

Leave architecture must distinguish entitlement rules, recurring increases,
one-time grants, lots/origin, consumption, carry-over, expiry, evidence/notices,
and ledger state. These are distinct responsibilities and facts, not a mandatory
list of database tables.

Rules and their effective versions determine entitlement. Recurring increases
and one-time grants have their own origins; they must not become indistinguishable
manual edits of a balance. Lots or equivalent origin tracking preserve which
entitlement was consumed, carried over, or expired and on what basis. Consumption
requires its own justified event. Carry-over and expiry preserve the applicable
rule version and necessary evidence/notices; a date alone must not assert that
all conditions for expiry were met.

Entitlement and remaining leave are derived from immutable ledger events and
applicable rules, with linked reversals/corrections and retained provenance.
A single mutable `remaining_days` value must not become authority. Units,
rounding, detailed accrual, lot allocation, notice workflows, and UI remain open.
A scheduling preference never silently grants or consumes leave.

### Tariff applicability and compensation provenance

Actual work, working-time accounting, and compensation remain separate.
Compensation may consume actual work, justified credit or non-work entitlement,
and other applicable inputs; it must not manufacture actual work or derive
monetary entitlement solely from a time-account balance.

Tariff applicability requires an established actual legal/contractual basis and
its effective validity and provenance. Geography, establishment, job label,
customer/site, or another convenient field may be relevant evidence but cannot
alone establish applicability. Unresolved applicability must remain unresolved
rather than silently selecting a tariff as authoritative.

Actual tariff classification and a **personal compensation floor** are different
facts. A personal floor does not change tariff classification or invent tariff
applicability. Personal, object/site, activity, and tariff compensation components
remain distinguishable inputs with their own basis and validity. Their precedence,
combination, and exact monetary rules require separately decided calculation
rules; this ADR fixes no rates or premium percentages.

Compensation calculations are versioned and reproducible from identified input
versions, the calculation-rule version, applicability/classification evidence,
and external-source provenance. Corrections retain the earlier calculation and
its basis. Recalculation using newer rules or corrected facts must be explicit;
it must not silently relabel an old result as computed under the new authority.

Tariff rates, premium values, statutory limits, legal rules, general binding
status (AVE), case law, and similar mutable external facts are **not timeless ADR
facts**. Their implementation or calculation use requires current verification
against the applicable authoritative source, effective dates, source/version
identity, verification provenance, and revalidation when that authority changes
or the prior evidence no longer supports the relevant period. Historical
calculations retain the historically applicable evidence; a newer source must
not silently replace it. Missing or ambiguous authority must prevent an
unsupported definitive calculation or compliance claim. No current legal or
tariff value is accepted by this record.

## Consequences

### Positive

- Rehire and future terms preserve employment history without conflating identity,
  membership, employment, or access.
- Work evidence, accounting, absence, leave, and compensation remain auditable
  without inventing performed work or mutating authoritative balances.
- Effective versions and provenance support reproducible historical decisions
  while keeping mutable legal/tariff facts outside permanent architecture claims.
- Scheduling can consume constraints without unnecessary HR/medical disclosure.

### Costs and remaining decisions

Temporal resolution, corrections, ledger reversals, historical reproducibility,
and cross-domain effects require explicit validation and domain ownership during
separately scoped implementation. This record does not accept a new generic
workflow engine, event-sourcing platform, or universal status model.

The complete scheduling model, every working-time compliance rule, exact statutory
limits, tariff entities/rates, compensation formulae, payroll export contracts,
Time Capture UX, leave/absence workflows, schema/table names, API contracts,
migration mechanics, and compatibility paths remain outside this decision.
An architectural concept here requires its invariant, not necessarily a new
permanent entity. ADR acceptance is neither delivered capability nor proof of
legal compliance. This issue performs organization documentation reconciliation
only; implementation and rollout remain separately owned.

## Alternatives considered

1. **Keep one authoritative Employee contract projection.** Rejected: it cannot
   serve as the decided period/terms authority across rehire and effective-dated
   history. A derived current view remains possible.
2. **Rewrite ADR-014's July decision body.** Rejected: it would misrepresent when
   the later architecture became accepted and erase truthful historical evidence.
3. **Use positioning or project-source prose as the new authority.** Rejected:
   accepted architecture must be changed explicitly through an ADR.
4. **Finalize all scheduling, legal, tariff, and payroll details here.** Rejected:
   those implementation and mutable-rule decisions exceed this contract.

## Related

- [Issue #841](https://github.com/SecPal/.github/issues/841): architecture-record
  delivery owner; positioning epic #761 does not decide this architecture.
- [ADR-014](20260720-tenant-identity-access-model-adr014.md): retained Tenant,
  identity, access, security, and lifecycle authority with the partial supersession
  defined above.
- [ADR-015](20260720-global-identity-key-security-adr015.md): unchanged Global
  Identity Key security authority.
- [Product positioning](../product-positioning.md) and
  [Public status semantics](../public-status-semantics.md): accepted architecture
  must not be promoted into implementation or availability claims.
