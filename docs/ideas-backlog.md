<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# SecPal Ideas & Future Concepts

**Purpose:** This document captures ideas, concepts, and features that are **not yet prioritized** but may become relevant later. Think of this as a "parking lot" for thoughts that don't warrant immediate action but shouldn't be forgotten.

**Status:** Living document - Add ideas freely, review quarterly

**Last Updated:** 2025-10-27

> **Note:** Core features (RBAC, Employee Management, Shift Planning) have been moved to `feature-requirements.md` for detailed specification. This document focuses on long-term/experimental ideas.

---

## 📱 Mobile Apps

### Idea: Native Mobile Apps for Guards

**Context:**
Guards in the field need quick access to the guard book while on patrol, often in areas with poor network connectivity.

**Concept:**

- Native iOS/Android apps (React Native or Flutter)
- Offline-first architecture with sync
- Biometric authentication (fingerprint, Face ID)
- Camera integration for incident photos
- GPS tracking for patrol routes
- NFC/QR code scanning for checkpoints

**When to revisit:**

- After web frontend reaches v1.0
- When field testing shows demand
- When budget allows native development

**Complexity:** High
**Priority:** Future (post-1.0)

**Related Issues:** _None yet_

---

## 🔐 Advanced Security Features

### Idea: Hardware Security Module (HSM) Integration

**Context:**
For maximum legal compliance, cryptographic operations (signatures, checksums) could use certified hardware.

**Concept:**

- Integration with HSM or cloud HSM (AWS CloudHSM, Azure Key Vault)
- Store signing keys in tamper-proof hardware
- Meet eIDAS Advanced Electronic Signature requirements
- Support for smartcard-based signatures

**When to revisit:**

- When targeting government/military contracts
- When eIDAS compliance becomes mandatory
- When commercial licensing generates revenue for hardware investment

**Complexity:** Very High
**Cost:** €5,000-50,000+ (hardware) + integration effort

**Related:**

- ADR-001 mentions digital signatures
- Future ADR needed for signature strategy

---

### Decision Made: OpenTimestamp (Blockchain-Based)

**Status:** ✅ **DECIDED** - See ADR-002

**Context:**
German law requires provable timestamps for guard book records (BewachV §10).

**Decision:**
Use **OpenTimestamp** instead of traditional RFC 3161 TSA for cost-effective, decentralized timestamping.

**Rationale:**

- ✅ Zero recurring costs (vs. €0.01-0.10/timestamp with TSA)
- ✅ Bitcoin blockchain as trust anchor (long-term verifiable)
- ✅ No vendor lock-in
- ⚠️ Not eIDAS "qualified timestamp" (but sufficient for BewachV §10)

**Next Steps:**

- Legal review confirms acceptability (Issue #46)
- Implement in Phase 3 of Event Sourcing (ADR-001)

**Alternative (Hybrid Approach):**
If legal review requires eIDAS compliance, we could use:

- OpenTimestamp for bulk events (cost-effective)
- RFC 3161 qualified timestamps for critical events only (shift handovers, legal disputes)

**Related:**

- ADR-002: OpenTimestamp for Audit Trail
- legal-compliance.md: BewachV requirements

---

## 🌍 Multi-Tenancy & SaaS

### Idea: Multi-Tenant SaaS Platform

**Context:**
Currently architecting for single organization. Future possibility: SaaS for multiple security companies.

**Architectural Questions:**

1. **Database per tenant** vs. **shared database with tenant_id**?
2. Event store isolation per tenant?
3. Backup/restore per tenant?
4. Custom branding per tenant?
5. Tenant-specific feature flags?

**When to revisit:**

- After first production deployment succeeds
- When approached by other security companies
- When considering VC funding / business model pivot

**Complexity:** Very High (architectural refactoring)

**Decisions needed:**

- Pricing model (per user, per shift, per entry?)
- Free tier vs. paid-only?
- Self-hosted option vs. cloud-only?

**Related:**

- ADR-001 mentions "Multi-tenancy: Separate event stores per organization?"

---

## 🤖 AI/ML Features

### Idea: Anomaly Detection in Guard Patrols

**Context:**
Machine learning could identify unusual patterns (missed patrols, unusual incident frequency, etc.)

**Concept:**

- Train ML model on historical patrol data
- Detect anomalies: Missed checkpoints, unusual times, pattern breaks
- Alert supervisors to potential issues
- Risk scoring for locations/times

**When to revisit:**

- After 6-12 months of production data
- When data volume justifies ML investment
- If client demand exists

**Complexity:** High
**Skills needed:** Data science, ML engineering

---

### Idea: Natural Language Processing for Incident Reports

**Context:**
Guards write incident descriptions in free text. NLP could extract structured data.

**Concept:**

- Use NLP to extract: Involved persons, time, location, incident type
- Auto-suggest tags/categories
- Sentiment analysis (escalation risk?)
- Multi-language support (German + English + ...)

**When to revisit:**

- After frontend includes rich text editor
- When incident volume justifies automation
- When affordable NLP APIs exist (GPT-4, Anthropic Claude)

**Cost:** API calls (€0.01-0.10 per incident?)

---

## 📊 Analytics & Reporting

### Idea: Advanced Analytics Dashboard

**Context:**
Security managers need insights beyond raw guard book entries.

**Features:**

- Incident heatmaps (time, location)
- Guard performance metrics
- Client-specific reports
- Predictive analytics (forecast high-risk periods)
- Cost per shift calculations
- KPI tracking (response times, patrol compliance)

**When to revisit:**

- After core guard book functionality is stable
- When user research shows demand
- When data volume allows meaningful analytics

**Complexity:** Medium-High

**Tech considerations:**

- Use dedicated analytics database? (ClickHouse, TimescaleDB)
- Data warehouse pattern?
- BI tool integration (Metabase, Superset)?

---

## 🔗 Integrations

### Idea: Integration with Access Control Systems

**Context:**
Many security services manage building access (key cards, biometric readers).

**Concept:**

- Integrate with access control APIs (SALTO, ASSA ABLOY, etc.)
- Log access events in guard book
- Cross-reference incidents with access logs
- Alert on unusual access patterns

**When to revisit:**

- When clients request this feature
- After core platform is stable

**Complexity:** Medium (depends on API availability)

---

### Idea: Emergency Services Integration

**Context:**
For serious incidents, guards need to contact police/fire/ambulance.

**Concept:**

- One-click emergency calls from mobile app
- Automatic location sharing
- Pre-fill incident details for dispatcher
- Track emergency response times
- Integration with German emergency numbers (110, 112)

**When to revisit:**

- When mobile apps exist
- When targeting high-security clients
- Legal review needed (liability!)

**Complexity:** High
**Legal risk:** High (emergency services integration is sensitive)

---

## 🌐 Internationalization

### Idea: Multi-Language Support

**Context:**
Currently German-focused. International expansion possible?

**Languages to consider:**

1. **English** (international clients, EU)
2. **French** (Switzerland, Belgium)
3. **Polish** (large security service market)
4. **Turkish** (large security worker population in Germany)

**When to revisit:**

- After German v1.0 is stable
- When international clients approach
- When budget allows translation

**Complexity:** Medium (i18n infrastructure + translations)

**Considerations:**

- Legal texts must be translated by professionals!
- Time zones (currently assuming Europe/Berlin)
- Different legal requirements per country

---

## 💼 Business Model Ideas

### Idea: White-Label Solution

**Context:**
Large security companies might want branded version.

**Concept:**

- Custom branding (logo, colors, domain)
- Feature selection per client
- Premium pricing tier
- Dedicated support

**When to revisit:**

- After successful v1.0 launch
- When approached by enterprise clients

---

### Idea: API Licensing for Integration Partners

**Context:**
Third parties (HR systems, billing software) might want to integrate.

**Concept:**

- Public API with rate limits
- API keys per partner
- Usage-based pricing
- Developer documentation portal
- SDK/client libraries (PHP, JavaScript, Python)

**When to revisit:**

- After API is stable (v1.0+)
- When partner interest exists

---

## 🔬 Research Topics

### Topic: GDPR "Right to Erasure" vs. Immutable Events

**Problem:**
Event sourcing is immutable, but GDPR requires ability to delete personal data.

**Solutions to research:**

1. **Crypto-shredding:** Encrypt events with user-specific key, delete key = data unreadable
2. **Tombstone events:** `user.personal_data.redacted` event replaces personal info
3. **Pseudonymization:** Store personal data separately, link via UUID, delete personal data but keep events
4. **Legal exception:** Is guard book exempt due to legal retention requirements?

**When to research:**

- Before v1.0 launch
- During legal review
- When GDPR audit happens

**Related:**

- Issue #46 (Legal Review)
- Future ADR needed

---

### Topic: Long-Term Archival (10+ Years)

**Problem:**
Events must be readable decades later. File formats, databases, encryption change.

**Solutions to research:**

1. **WORM storage** (Write-Once-Read-Many) - AWS Glacier, tape libraries
2. **PDF/A format** for exports (ISO 19005, archival standard)
3. **Migration strategy:** Periodic re-export to newer formats
4. **Blockchain anchoring:** Store merkle root in public blockchain

**When to research:**

- Before first long-term contracts
- During legal review
- When planning storage budget

---

### Topic: Offline-First Architecture

**Problem:**
Guards may have no internet in basements, remote areas.

**Solutions to research:**

1. **Conflict-free Replicated Data Types (CRDTs)** for offline sync
2. **PouchDB/CouchDB** for offline storage + sync
3. **Service Workers** for web app offline capability
4. **Operational Transformation** for concurrent editing

**When to research:**

- Before mobile app development
- When field testing shows connectivity issues

---

## 📝 Documentation Improvements

### Idea: Interactive API Documentation

**Concept:**

- Swagger UI / Redoc for OpenAPI spec
- Try-it-out feature with live API
- Code examples in multiple languages
- Postman collection

**When to revisit:**

- After API v1.0 is stable
- When external developers need access

---

### Idea: Video Tutorials / Screencasts

**Concept:**

- Onboarding videos for new guards
- Admin training videos
- Developer setup walkthroughs

**When to revisit:**

- After user testing shows onboarding friction
- When budget allows video production

---

## 🧪 Technical Experiments

### Experiment: PostgreSQL NOTIFY/LISTEN for Real-Time Updates

**Concept:**
Use PostgreSQL's pub/sub for real-time features without Redis/WebSockets complexity.

**When to try:**

- During spike/exploration phase
- When real-time features needed (live dashboard)

---

### Experiment: Laravel Octane for Performance

**Concept:**
Run Laravel with Swoole/RoadRunner for massive performance gains.

**When to try:**

- After performance profiling shows bottlenecks
- When scaling becomes necessary

---

## 🛠️ Developer Experience

### Idea: GitHub Codespaces / Dev Containers

**Concept:**

- One-click development environment in browser
- No local setup needed
- Consistent environment across developers

**When to revisit:**

- When onboarding new contributors
- When development setup becomes complex

---

### Idea: Automated Dependency Updates with Auto-Merge

**Concept:**

- Renovate Bot (see Issue #52) with auto-merge for patch versions
- Reduce maintenance burden

**When to revisit:**

- After v1.0 when test coverage is high
- When dependency updates become burdensome

---

## 💬 Community & Open Source

### Idea: Open Source Community Building

**Concept:**

- Good first issue labels
- Contributor recognition (all-contributors bot)
- Regular contributor calls
- Roadmap voting

**When to revisit:**

- When project gains external interest
- After v1.0 launch

---

## 🎓 How to Use This Document

1. **Add ideas freely** - No idea is too wild for this doc
2. **Don't delete ideas** - Mark as "Rejected" or "Superseded" instead
3. **Review quarterly** - Move actionable items to GitHub Issues
4. **Link to Issues/ADRs** - When ideas become concrete
5. **Capture context** - Why did you think of this? What problem does it solve?

---

## 📌 Template for New Ideas

```markdown
### Idea: [Short Title]

**Context:**
[Why are you thinking about this?]

**Concept:**
[What would it look like?]

**When to revisit:**
[Triggers for reconsidering]

**Complexity:** Low | Medium | High | Very High
**Priority:** Now | Soon | Later | Future | Research

**Related:**

- Issue #...
- ADR-...
```

---

**Next Actions:**

- Move Event Sourcing idea → ADR-001 ✅ Done
- Review this doc every 3 months
- Create GitHub Issues for "Now" or "Soon" priorities
