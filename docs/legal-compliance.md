<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Legal & Regulatory Compliance

**Purpose:** This document outlines all legal, regulatory, and normative requirements that SecPal must comply with.

**Target Audience:** Developers, legal advisors, auditors, certification bodies

**Status:** Living document - Update when new requirements identified

**Last Updated:** 2025-10-27

---

## 🇪🇺 GDPR (General Data Protection Regulation)

**Regulation:** EU 2016/679 (DSGVO in German)

**Applicability:** ✅ Mandatory (SecPal processes personal data)

### Data Subject Rights

**Article 15-22 Rights:**

| Right                  | SecPal Implementation                           | Status      |
| ---------------------- | ----------------------------------------------- | ----------- |
| **Access** (Art. 15)   | Export user data via API endpoint               | ⏳ Planned  |
| **Rectification** (16) | Edit profile, update entries (with audit trail) | ⏳ Planned  |
| **Erasure** (17)       | Pseudonymization + crypto-shredding (see below) | 🔬 Research |
| **Portability** (20)   | Export JSON/CSV via API                         | ⏳ Planned  |
| **Object** (21)        | Opt-out of analytics, marketing                 | ⏳ Planned  |

### Right to Erasure vs. Legal Retention

**Conflict:** GDPR "right to erasure" vs. BewachV §10 "2-year retention requirement"

**Resolution:**

```
Art. 17(3)(b) GDPR: Erasure not applicable when processing is necessary:
"for compliance with a legal obligation which requires processing
by Union or Member State law"
```

**SecPal approach:**

1. **Guard book entries:** Retained per BewachV §10 (legal exemption from erasure)
2. **Personal data:** Pseudonymized after retention period
3. **Optional data:** (marketing consent, analytics) - erasable immediately

**Implementation (Crypto-Shredding):**

```php
use Illuminate\Support\Facades\Crypt;

// Encrypt personal data with Laravel's Crypt facade
$encryptedName = Crypt::encryptString($user->name);

// On erasure request (crypto-shredding approach):
// Delete user's encryption key to make data unreadable
DB::table('users')->where('id', $user->id)->update([
    'encryption_key' => null, // Delete key = data unreadable
    'name' => null,
    'email' => 'deleted-' . hash('sha256', $user->id) . '@deleted.local',
]);

// Guard book events remain, but personal data is unrecoverable
```

### Data Processing Records (Art. 30)

**Required:** Register of processing activities

**SecPal categories:**

1. **User authentication** (legal basis: Contract - Art. 6(1)(b))
2. **Guard book entries** (legal basis: Legal obligation - Art. 6(1)(c) + BewachV)
3. **Incident photos** (legal basis: Legitimate interest - Art. 6(1)(f))
4. **Analytics** (legal basis: Consent - Art. 6(1)(a))

**Documentation:** Maintain in `.github/docs/gdpr-processing-register.md` (to be created)

### Data Protection by Design (Art. 25)

**Measures implemented:**

- ✅ Encryption at rest (database encryption)
- ✅ Encryption in transit (HTTPS/TLS only)
- ✅ Access control (RBAC - role-based)
- ✅ Audit logging (event sourcing)
- ✅ Data minimization (only collect necessary data)
- ✅ Pseudonymization (separate personal data from operational data)

### Breach Notification (Art. 33-34)

**Requirement:** Notify supervisory authority within **72 hours** of breach

**SecPal process:**

1. Detect breach (monitoring/alerts)
2. Assess severity (GDPR Art. 33(1) criteria)
3. Notify authority (if high risk): <https://www.bfdi.bund.de/>
4. Notify affected users (if high risk to rights/freedoms)
5. Document in breach register

**Next Steps:**

- [ ] Create incident response plan
- [ ] Define breach severity matrix
- [ ] Designate data protection officer (DPO) contact

---

## 🇩🇪 BewachV (Bewachungsverordnung)

**Regulation:** German ordinance on security services (Verordnung über das Bewachungsgewerbe)

**Applicability:** ✅ Mandatory (SecPal targets German security services)

### §7-9 Documentation Requirements

**§7 Bewachungsregister (Security Service Register):**

Not directly applicable (SecPal is not a security service provider, but a tool vendor).

**§8 Dienstanweisung (Service Instructions):**

Security companies must provide service instructions to guards. SecPal can **facilitate** this but doesn't replace legal obligation.

**§9 Aufzeichnungen (Records):**

> "Der Gewerbetreibende hat über jeden Bewachungsauftrag Aufzeichnungen zu fertigen."
>
> (The entrepreneur must make records for each security assignment.)

**Required information:**

1. Client name and address
2. Type of security service
3. Start and end time of service
4. Number of deployed guards
5. Special incidents

**SecPal implementation:**

```php
// Guard shift model includes BewachV-required fields
Schema::create('guard_shifts', function (Blueprint $table) {
    $table->uuid('id')->primary();

    // BewachV §9 required fields
    $table->string('client_name'); // Auftraggeber
    $table->text('client_address');
    $table->enum('service_type', [
        'object_protection',    // Objektschutz
        'person_protection',    // Personenschutz
        'event_security',       // Veranstaltungsschutz
        'patrol',               // Streifendienst
        'alarm_response',       // Interventionsdienst
    ]);
    $table->timestampTz('started_at');
    $table->timestampTz('ended_at')->nullable();
    $table->integer('guard_count')->unsigned();

    // Additional SecPal fields
    $table->text('special_incidents')->nullable();
    $table->jsonb('location');
    $table->timestamps();
});
```

### §10 Aufbewahrung (Retention)

> "Die Aufzeichnungen nach §9 sind mindestens zwei Jahre aufzubewahren."
>
> (Records per §9 must be retained for at least two years.)

**SecPal implementation:**

- ✅ Event sourcing ensures immutability
- ✅ OpenTimestamp proves chronology
- ✅ Automated archival after 2 years (move to cold storage, but retain)
- ✅ Export capability for regulatory inspections

**Retention policy:**

```php
// app/Console/Commands/ArchiveOldShifts.php
class ArchiveOldShifts extends Command {
    public function handle() {
        $twoYearsAgo = now()->subYears(2);

        $oldShifts = GuardShift::where('ended_at', '<', $twoYearsAgo)
                               ->where('archived', false)
                               ->get();

        foreach ($oldShifts as $shift) {
            // Export to PDF + OTS proof
            $pdf = PDF::make($shift);
            $pdf->saveToArchive("shifts/archived/{$shift->id}.pdf");

            // Mark as archived (don't delete!)
            $shift->update(['archived' => true]);
        }
    }
}
```

### §11 Vorlage der Aufzeichnungen (Presentation of Records)

> "Der Gewerbetreibende hat die Aufzeichnungen [...] der zuständigen Behörde auf Verlangen vorzulegen."
>
> (The entrepreneur must present records to the competent authority on request.)

**SecPal features:**

- ✅ Export shifts to PDF (with OpenTimestamp proof)
- ✅ Filter by date range, client, guard
- ✅ Include all BewachV-required information
- ✅ Cryptographic verification instructions included

**Implementation:**

- Compliance export endpoint: `POST /api/v1/employees/{employee}/bwr/export`
- Returns ZIP with PDFs + OTS proofs + verification guide

---

## 📐 DIN 77200 (Security Services)

**Standard:** DIN 77200-1 to DIN 77200-10 series

**Applicability:** ⚠️ Optional (but recommended for competitive advantage)

**Status:** Certification not mandatory, but many clients require it

### DIN 77200-1: Basic Requirements

**Section 4.2.3 Documentation:**

> "Der Sicherheitsdienstleister muss ein Dokumentationssystem vorhalten, das die Nachvollziehbarkeit der Leistungserbringung sicherstellt."
>
> (The security service provider must maintain a documentation system that ensures traceability of service delivery.)

**SecPal alignment:**

- ✅ Comprehensive documentation (guard book, incidents, patrols)
- ✅ Traceability via event sourcing
- ✅ Tamper-proof via OpenTimestamp + chaining

**Section 5.1.5 Quality Management:**

Requires documented processes for:

- Service delivery
- Incident handling
- Client communication
- Internal audits

**SecPal support:**

- 📋 Templates for standard operating procedures (SOPs)
- 📊 Metrics dashboard (KPIs for quality management)
- 🔍 Audit trail export

### DIN 77200-6: Alarm Response Services

If targeting alarm response market, additional requirements:

- Response time logging (⏳ Planned)
- Key management tracking (🔬 Future)
- False alarm documentation (⏳ Planned)

**Complexity:** Medium
**Priority:** Low (focus on basic guard book first)

---

## 🏆 ISO 9001 (Quality Management)

**Standard:** ISO 9001:2015

**Applicability:** ⚠️ Optional (but valuable for B2B clients)

**Certification:** Requires external audit (e.g., TÜV, DQS)

### Relevant Clauses for SecPal

**Clause 7.5 Documented Information:**

> "The organization shall control documented information to ensure it is adequately protected."

**SecPal compliance:**

- ✅ Version control (Git)
- ✅ Access control (RBAC)
- ✅ Backup/disaster recovery
- ✅ Audit trail

**Clause 8.5.1 Control of Production and Service Provision:**

> "The organization shall implement processes to ensure that all requirements are met."

**SecPal features:**

- Checklists for patrol routes
- Required fields for incident reports
- Validation before submission
- Manager approval workflows

**Clause 9.1.3 Analysis and Evaluation:**

> "The organization shall analyze and evaluate appropriate data from monitoring and measurement."

**SecPal analytics:**

- Incident frequency analysis
- Guard performance metrics
- Client satisfaction tracking
- Trend reports

### ISO 9001 Certification Path

**If SecPal targets ISO 9001-certified clients:**

1. **Internal audit:** Self-assess against ISO 9001 requirements
2. **Gap analysis:** Identify missing processes/documentation
3. **Implement QMS:** Document all processes
4. **External audit:** Hire certification body (TÜV, DQS, etc.)
5. **Certification:** Maintain through annual surveillance audits

**Estimated effort:** 6-12 months
**Cost:** €5,000-15,000 (initial) + €2,000-5,000 annual

**Priority:** 🔮 Future (when targeting enterprise clients)

---

## 🔒 NIS2 (Network and Information Security Directive)

**Directive:** EU 2022/2555 (NIS2)

**Applicability:** ⚠️ Potentially (if SecPal becomes "essential service")

**Threshold:**

- €10M+ annual revenue, OR
- 50+ employees, OR
- Classified as "critical infrastructure"

**Status:** 🔬 Monitor - Not applicable yet, but plan ahead

**If applicable, requires:**

- Incident reporting to CERT-Bund
- Security risk management
- Supply chain security
- Cybersecurity training

**SecPal preparation:**

- ✅ Already implementing security best practices (GHAS, CodeQL)
- ⏳ Formal incident response plan (to be documented)
- 🔮 Supply chain security (SBOM generation with CycloneDX)

---

## 📊 Compliance Matrix

| Requirement     | Status      | Priority | Next Action                        |
| --------------- | ----------- | -------- | ---------------------------------- |
| GDPR Art. 15-22 | ⏳ Planned  | P1 High  | Implement data export API          |
| GDPR Art. 25    | ✅ Partial  | P1 High  | Document encryption architecture   |
| GDPR Art. 30    | 📝 Draft    | P1 High  | Create processing register         |
| GDPR Art. 33-34 | 🔬 Research | P1 High  | Draft incident response plan       |
| BewachV §9      | ✅ Designed | P0 Block | Implement guard shift model        |
| BewachV §10     | ✅ Designed | P0 Block | Implement 2-year retention         |
| BewachV §11     | ⏳ Planned  | P1 High  | Build compliance export API        |
| DIN 77200-1     | 🔬 Research | P2 Med   | Gap analysis vs. standard          |
| ISO 9001        | 🔮 Future   | P3 Low   | Consider for v2.0+ (if B2B demand) |
| NIS2            | 🔬 Monitor  | P3 Low   | Reassess when revenue grows        |

**Legend:**

- ✅ Implemented
- ⏳ Planned (roadmap)
- 🔬 Research (investigating)
- 📝 Draft (documentation in progress)
- 🔮 Future (post-1.0)

---

## 🧑‍⚖️ Legal Review Checklist

**Before production launch:**

- [ ] **GDPR:** Review with data protection lawyer
- [ ] **BewachV:** Confirm compliance with security service law expert
- [ ] **DIN 77200:** Optional - gap analysis if targeting certified clients
- [ ] **Terms of Service:** Draft ToS with IT lawyer
- [ ] **Privacy Policy:** GDPR-compliant privacy policy
- [ ] **Data Processing Agreement (DPA):** For B2B clients (Art. 28 GDPR)
- [ ] **Cookie Policy:** If using analytics cookies

**Recommended law firms:**

- JBB Rechtsanwälte (Berlin) - IT law + GDPR
- iRights Law (Munich) - Open source + tech
- Bird & Bird (Düsseldorf) - Data protection specialists

**Estimated cost:** €3,000-10,000 (one-time legal review)

---

## 📚 Reference Documents

### German Law

- [BewachV (Full Text)](https://www.gesetze-im-internet.de/bewachv/)
- [GewO §34a (Security Service Licensing)](https://www.gesetze-im-internet.de/gewo/__34a.html)
- [BDSG (German Data Protection Act)](https://www.gesetze-im-internet.de/bdsg_2018/)

### EU Regulations

- [GDPR (Official Text)](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
- [NIS2 Directive](https://eur-lex.europa.eu/eli/dir/2022/2555)

### Standards

- [DIN 77200 Overview](https://www.beuth.de/de/norm/din-77200-1/298973684)
- [ISO 9001:2015](https://www.iso.org/standard/62085.html)

### Data Protection Authorities

- [BfDI (German Federal DPA)](https://www.bfdi.bund.de/)
- [EDPB (European Data Protection Board)](https://edpb.europa.eu/)

---

## 🔄 Review Schedule

**Quarterly review:** Check for new regulations/standards

**Annual review:** Update compliance matrix

**Triggered review:** When entering new markets (other EU countries, USA, etc.)

**Responsibility:** Legal team (when exists) or external counsel

---

## Related

- Issue #46: Legal Review of CLA and Commercial Licenses
- ADR-001: Event Sourcing (ensures BewachV §10 retention)
- ADR-002: OpenTimestamp (provides tamper-proof evidence)
- ADR-003: Offline-First (no data loss = compliance)
- `ideas-backlog.md`: GDPR "right to erasure" research

---

**Next Steps:**

1. Schedule legal review (pre-v1.0)
2. Create GDPR processing register
3. Draft privacy policy + ToS
4. Implement BewachV-compliant data model
5. Build compliance export API
