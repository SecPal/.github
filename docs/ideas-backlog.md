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

## 🏢 Sub-Contractor Management

### Idea: Multi-Level Subcontractor Hierarchy

**Context:**
Security companies frequently collaborate with subcontractors who provide personnel for specific sites or shifts. These subcontractors must also be managed, qualified, and billed separately.

**Concept:**

- **Hierarchical Company Structure:**
  - Prime Contractor (main company)
  - Subcontractors - multiple levels possible
  - Separate cost centers and billing
- **Subcontractor Profile:**
  - Company name, registration, IHK number (German Chamber of Commerce)
  - Contact persons, contracts, insurance policies
  - Authorized activity areas
  - Rating/evaluation (quality, reliability)
- **Personnel Assignment:**
  - Employees belong to subcontractor
  - Automatic labeling in shift schedules
  - Separate billing per subcontractor
- **Compliance:**
  - Verification of subcontractor licenses
  - Minimum standards for qualifications
  - Liability issues, insurance verification
- **Reporting:**
  - Costs broken down by subcontractor
  - Deployment statistics per subcontractor
  - Performance metrics

**When to revisit:**

- After Employee Management v1.0
- When client projects require subcontractors
- Coordinate with legal/tax advisors

**Complexity:** High (Multi-Tenancy, Hierarchies, Billing Logic)
**Priority:** Later (Phase 3-4)

**Related:**

- Employee Management (Core Feature)
- Shift Planning (Core Feature)
- Client Portal (ideas-backlog.md)

---

## 🆔 BWR Integration (Security Service Register)

### Idea: BWR Registry Integration in Employee Records

**Context:**
According to §11b BewachV (German Security Services Act), security companies must ensure their employees are registered in the Bewachungsregister (BWR - Security Service Register). Manual verification is error-prone and time-consuming.

**Concept:**

- **BWR-ID in Employee Record:**
  - Required field for employees with guard responsibilities
  - Automatic format validation
  - Link to IHK portal (if API available)
- **BWR Status Tracking:**
  - Status: `active`, `suspended`, `expired`, `not_registered`
  - Registration expiry date
  - Automatic notifications before expiry (30/60/90 days advance)
  - Block shift planning if status invalid
- **Activity Areas (§34a GewO Paragraphs):**
  - Paragraph 1: Patrol duties (all guards)
  - Paragraph 2: Protection against shoplifting
  - Paragraph 3: Security at entry areas (bouncers)
  - Paragraph 4: Security at refugee accommodations
  - Paragraph 5: City patrol
  - Mapping to SecPal qualifications
- **Compliance Dashboard:**
  - Overview: How many employees have valid BWR entries?
  - Warnings for expiring registrations
  - Reports for authorities/clients
- **Optional: API Integration (if available):**
  - Automatic synchronization with IHK database
  - Real-time status updates
  - Eliminate manual data entry

**When to revisit:**

- After Employee Management v1.0
- When official BWR-API becomes available
- Coordinate with IHK/authorities

**Complexity:** Medium (Data Model) to High (with API)
**Priority:** Soon (important for compliance!)

**Related:**

- Employee Management (Core Feature)
- Qualifications System (Core Feature)
- Legal Compliance (docs/legal-compliance.md)
- Issue #... (to be created for detailed specification)

**Technical Notes:**

- BWR-ID Format: Check if standardized format exists
- Data Privacy: Clarify if BWR status is personal data (GDPR)
- API: Check IHK-API availability (may be manual only)

---

## 📅 Advanced Shift Planning Features

### Idea: (Semi-)Automated Shift Planning with Employee Suggestions

**Context:**
Manual shift planning is time-consuming. Managers need support to find available employees who meet all requirements (qualifications, working time law, preferences). Current `feature-requirements.md` includes basic auto-scheduling, but advanced AI-driven suggestions are not yet specified.

**Concept:**

**1. Intelligent Employee Suggestions:**

- **Context-Aware Recommendations:**
  - Manager starts planning a shift (e.g., "Night shift, Object A, 22:00-06:00")
  - System analyzes requirements: Qualifications (§34a, First Aid), location, time
  - System suggests **ranked list** of suitable employees:

```
🟢 Max Mustermann (Optimal Match)
   ✅ §34a certification valid
   ✅ First Aid certification valid
   ✅ Available (no vacation, no conflicting shift)
   ✅ Preferred shift time (marked "Night shifts OK")
   ✅ Recently worked at Object A (familiar with location)
   💰 Regular rate (no overtime premium)

🟡 Anna Schmidt (Good Match)
   ✅ §34a certification valid
   ✅ First Aid certification valid
   ✅ Available (no conflicts)
   ⚠️ Prefers day shifts (but not blocked)
   ⚠️ New to Object A (requires briefing)
   💰 Regular rate

🔴 Tom Müller (Possible, but issues)
   ✅ §34a certification valid
   ❌ First Aid expired (needs renewal)
   ⚠️ Would exceed 48h/week (requires approval)
   ⚠️ Last shift ended 10h ago (min 11h rest period)
```

**2. AI-Powered Optimization:**

- **Machine Learning Suggestions:**
  - Learn from historical data: "Max and Anna work well together"
  - Predict employee availability based on patterns
  - Optimize for cost (minimize overtime, travel expenses)
  - Fairness algorithm: Distribute unpopular shifts equitably
- **Multi-Week Planning:**
  - Plan entire month in one go
  - System generates multiple scenarios
  - Manager reviews and adjusts
- **Conflict Resolution:**
  - Highlight conflicts before they occur
  - Suggest alternative assignments
  - Explain why certain assignments are not possible

**3. Rule-Based Constraints:**

- **Hard Constraints (must be met):**
  - Working Time Law (ArbZG): Max 10h/day, 48h/week average
  - Rest periods: Min 11h between shifts
  - Qualifications: Must have required certificates
  - Availability: Not on vacation, not sick
- **Soft Constraints (preferred but not mandatory):**
  - Employee preferences (preferred times, locations)
  - Familiarity with location (worked there before)
  - Team composition (prefer known team members)
  - Cost optimization (avoid overtime if possible)

**4. "What-If" Scenarios:**

- Manager can test different configurations
- "What if Anna takes vacation on 05.11?"
- System recalculates and shows impact
- Helps with contingency planning

**When to revisit:**

- After basic shift planning (feature-requirements.md) is implemented
- When historical data is available for ML training
- When managers report bottlenecks in manual planning

**Complexity:** Very High (AI/ML, Optimization Algorithms)
**Priority:** Later (Phase 3-4, after MVP)

**Technical Notes:**

- Could use constraint satisfaction problem (CSP) solvers
- ML models require 6-12 months of historical data
- Consider external libraries: OR-Tools (Google), OptaPlanner, etc.

---

### Idea: Shift Plan Distribution via Push Notifications & Email

**Context:**
Employees need timely notification when new shift plans are published. While basic email notifications are mentioned in `feature-requirements.md`, advanced distribution features are not yet specified.

**Concept:**

**1. Multi-Channel Notifications:**

- **Email Notifications:**
  - Automatic email when shift plan is published
  - Include PDF attachment of personal schedule
  - Link to web/mobile app for details
  - Customizable templates (per organization)
- **Push Notifications (Mobile App):**
  - Instant notification when shift plan changes
  - Reminder 24h before shift starts
  - Badge count on app icon for unread shifts
- **SMS Notifications (Optional):**
  - Fallback for employees without smartphones
  - Short summary: "Your shift: Mon 04.11, 22:00-06:00, Object A"
  - Billable feature (SMS costs)

**2. Notification Triggers:**

- **Shift Plan Published:**
  - "Your shift plan for November 2025 is now available"
  - List all assigned shifts
- **Shift Changed:**
  - "Your shift on 05.11 has been changed"
  - Show old vs. new time/location
- **Shift Swapped:**
  - "Your shift swap request was approved"
  - Confirm new assignment
- **Shift Reminder:**
  - "Reminder: Your shift starts in 24 hours"
  - Include location, time, special instructions
- **Understaffed Shift Alert:**
  - "Urgent: Can you cover a shift on 07.11?"
  - Voluntary pickup opportunity (with bonus pay?)

**3. Personalization & Preferences:**

- **Employee Preferences:**
  - Opt in/out of specific notification types
  - Choose preferred channels (email, push, SMS)
  - Set "Do Not Disturb" hours (no notifications at night)
- **Language Support:**
  - Multilingual templates (German, English, Turkish, Polish, etc.)
  - Automatic language detection based on employee profile

**4. Delivery Tracking:**

- **Audit Log:**
  - Track when notification was sent
  - Track when employee read notification (push: opened app, email: tracking pixel)
  - Proof of delivery for legal disputes
- **Failed Delivery Alerts:**
  - If email bounces or push token invalid
  - Manager gets alert to contact employee directly

**When to revisit:**

- After mobile app is launched (Phase 2)
- When organizations report communication issues
- When legal requirements demand proof of notification

**Complexity:** Medium (Infrastructure for Push/SMS)
**Priority:** Soon (Phase 2, after basic shift planning)

**Technical Notes:**

- Push: Firebase Cloud Messaging (FCM) or Apple Push Notification Service (APNs)
- SMS: Twilio, AWS SNS, or local provider
- Email: Laravel Mail with queue for batch sending

---

### Idea: Mass Communication & Broadcast Messaging

**Context:**
Managers need to send important information to all employees or specific groups (e.g., "Office closed due to weather," "New safety policy," "Meeting invitation"). Email lists are cumbersome and lack targeting.

**Concept:**

**1. Broadcast Messaging System:**

- **Create Broadcast Message:**
  - Subject & body (rich text editor)
  - Optional: Attach files (PDF, images)
  - Optional: Mark as urgent (high priority notification)
- **Target Audience Selection:**
  - **All Employees:** Company-wide announcement
  - **By Location/Object:** "All employees at Object A"
  - **By Qualification:** "All §34a certified guards"
  - **By Employment Type:** "All full-time employees"
  - **By Branch Office:** "All employees in Berlin office"
  - **By Team/Manager:** "All employees under Manager X"
  - **Custom Selection:** Manually select individual employees

**2. Delivery Channels:**

- **Email (Primary):**
  - HTML email with organization branding
  - Automatic fallback to plain text
- **Mobile App Push Notification:**
  - Short summary in notification
  - Full message in app inbox
- **In-App Inbox:**
  - Persistent message history
  - Mark as read/unread
  - Archive old messages

**3. Read Receipts & Acknowledgment:**

- **Optional Acknowledgment:**
  - "Please acknowledge that you have read this message"
  - Employees must click "I have read and understood"
  - Manager sees list of who acknowledged
- **Delivery Statistics:**
  - Sent: 150 employees
  - Delivered: 148 (2 bounced emails)
  - Read: 120 (80% open rate)
  - Acknowledged: 95 (if acknowledgment required)

**4. Scheduled Broadcasts:**

- **Schedule for Later:**
  - Compose message now, send tomorrow at 08:00
  - Useful for announcements during office hours
- **Recurring Messages:**
  - "Monthly safety reminder" (auto-send on 1st of each month)
  - "Weekly schedule preview" (auto-send every Friday)

**5. Templates & Quick Actions:**

- **Predefined Templates:**
  - "Office closure announcement"
  - "Weather alert"
  - "Policy update notification"
  - "Meeting invitation"
- **Quick Filters:**
  - "Last-minute shift coverage needed" → Auto-targets available employees

**6. Compliance & Legal:**

- **Audit Trail:**
  - Who sent the message, when, to whom
  - Who read it, who acknowledged it
  - Legal proof for important communications (e.g., policy changes)
- **Unsubscribe Handling:**
  - Employees can opt out of **non-essential** messages
  - But **cannot** opt out of critical/legal messages (policy updates, safety alerts)

**When to revisit:**

- After basic employee management is in place (Phase 1)
- When organizations request "mass email" feature
- When mobile app inbox is available

**Complexity:** Medium (Email queuing, targeting logic, read receipts)
**Priority:** Soon (Phase 2, high user demand)

**Technical Notes:**

- Laravel Notifications for multi-channel support
- Queue system for batch email sending (avoid rate limits)
- Database tables: `broadcasts`, `broadcast_recipients`, `broadcast_reads`
- Consider integration with external newsletter tools (Mailchimp, SendGrid) for advanced features

**Example Use Cases:**

1. **Weather Emergency:**
   - "Due to heavy snowfall, Object B is closed today. Scheduled employees will be reassigned."
   - Target: All employees scheduled for Object B today
   - Urgent flag: Yes
   - Channels: Email + Push + SMS

2. **Policy Update:**
   - "New GDPR training required for all employees. Deadline: 30.11.2025."
   - Target: All active employees
   - Acknowledgment required: Yes
   - Channels: Email + In-App Inbox
   - Attach: PDF of new policy

3. **Shift Coverage Request:**
   - "Urgent: Looking for volunteer to cover night shift on 05.11 at Object A."
   - Target: Employees with §34a, available on 05.11, prefer night shifts
   - Channels: Push notification + Email
   - Quick action: "I can cover this shift" button

---

## 👔 Uniform & Clothing Management

### Idea: Multi-Location Clothing Warehouse Management

**Context:**
Security companies must provide uniforms and equipment to employees. With multiple branch offices, managing clothing inventory, sizes, issuance, and returns becomes complex. Additionally, permissions must be managed so that employees can only access their respective locations.

**Concept:**

**1. Clothing Warehouse Structure:**

- **Multi-Location Support:**
  - Multiple warehouses/rooms (e.g., per branch office, regional office)
  - Each location has its own inventory
  - Inter-location transfers trackable
  - Hierarchical structure: Headquarters → Regional offices → Branch offices

**2. Employee Clothing Sizes:**

- **Size Profile per Employee:**
  - Shirt (neck, sleeve length)
  - Pants (waist, length, inseam)
  - Jacket (chest, sleeve length, height)
  - Shoes (EU size, width)
  - Hat/cap (head circumference)
  - Special requirements (tall sizes, wide sizes, specific fits)
- **Size History:**
  - Track size changes over time
  - Helpful for reorders
  - Notice trends (seasonal weight changes)

**3. Inventory Management:**

- **Item Types:**
  - Uniform shirts/blouses
  - Pants/trousers
  - Jackets (summer/winter)
  - Safety vests/reflective gear
  - Shoes/boots
  - Accessories (belts, ties, badges, name tags)
  - PPE (Personal Protective Equipment)
- **Clothing Catalog (Available Items):**
  - Master catalog of generally orderable items
  - Item specifications (material, colors, sizes available)
  - Standard vs. special order items
  - Seasonal availability
  - Discontinued items marking
  - Replacement/successor items
- **Stock Management:**
  - Current inventory per location and size
  - Minimum stock levels with warnings
  - Reorder suggestions based on distribution
  - Cost tracking per item
- **Multiple Suppliers per Item:**
  - Primary and alternative suppliers
  - Price comparison per supplier
  - Lead times per supplier
  - Quality ratings/reviews
  - Automatic supplier selection (cheapest/fastest/preferred)
  - Supplier contact information and terms

**4. Issuance Management:**

- **Issue Tracking:**
  - Who received which items when
  - New vs. used condition documentation
  - Deposit system (if applicable - refundable upon return)
  - Photo documentation of condition
- **Employee Receipt/Acknowledgment:**
  - Digital signature on tablet/mobile device
  - Email confirmation with issued items list
  - PDF receipt generation for employee records
  - Timestamp and issuer documentation
  - Optional: Photo of employee with issued items
  - Multi-language support (German, English, Turkish, Polish)
- **Return Management:**
  - Return upon termination/transfer
  - Condition assessment (good/worn/damaged)
  - Cleaning required before return?
  - Lost items handling
  - Replacement costs billing
  - Return receipt/confirmation for employee

**5. Maintenance & Lifecycle:**

- **Cleaning Cycles:**
  - Track when items were cleaned
  - Schedule regular maintenance
  - External laundry service integration?
- **Wear & Replacement:**
  - Track usage duration
  - Automatic replacement intervals (e.g., every 12 months)
  - Damage/defect logging
  - Repair tracking

**6. Ordering & Procurement:**

- **Order Status Tracking:**
  - Status: `draft`, `pending_approval`, `ordered`, `partially_delivered`, `delivered`, `cancelled`
  - Expected delivery date
  - Partial deliveries tracking
  - Backorder management
  - Delivery confirmations
  - Automatic notifications on status changes
- **Bulk Orders:**
  - Automatic collection of requirements from all locations
  - Size distribution analysis for optimal ordering
  - Order history and lead times
- **Cost Centers (if applicable):**
  - Assign orders to specific cost centers
  - Cost center budget tracking
  - Approval workflows per cost center
  - Cost center reporting (per location, per department)
  - Budget alerts when limits approached
  - Split orders across multiple cost centers
- **Supplier Selection:**
  - Choose from multiple suppliers per item
  - Automatic best-price selection
  - Preferred supplier designation
  - Emergency/fallback suppliers
  - Supplier performance tracking
- **Just-in-Time vs. Stock:**
  - Balance between storage costs and availability
  - Seasonal planning (winter jackets, summer shirts)

**7. Multi-Location Permissions & Access Control:**

- **Role-Based Access Control (RBAC):**
  - **View permissions:**
    - See all locations (HQ management)
    - See only specific locations (regional managers)
    - See only own location (branch managers)
  - **Edit permissions:**
    - Manage all locations (HQ warehouse manager)
    - Manage specific locations only (regional warehouse staff)
    - Issue items at own location (branch office staff)
    - View-only access (accountants, auditors)
  - **Special permissions:**
    - Inter-location transfers (specific role)
    - Order approval workflows
    - Inventory adjustment authorization
- **Audit Trail:**
  - Every action logged (who, what, when, where)
  - Stock discrepancies traceable
  - Accountability for issued items

**8. Reporting & Analytics:**

- **Stock Reports:**
  - Current inventory by location/size/item
  - Stock value per location
  - Inventory turnover rate
- **Issuance Reports:**
  - Most frequently issued items
  - Return compliance rate
  - Outstanding items per employee
- **Cost Analysis:**
  - Clothing costs per employee
  - Costs per location
  - Budget vs. actual spending
- **Compliance:**
  - All employees properly equipped?
  - Missing sizes/items?
  - Expired PPE items?

**When to revisit:**

- After Employee Management v1.0 is complete
- When client feedback indicates demand
- When multiple branch offices are operational
- After RBAC system is fully implemented

**Complexity:** High (Multi-location, inventory tracking, permissions)
**Priority:** Later (Phase 3-4)

**9. Service ID Cards (Dienstausweise) Management:**

- **ID Card Lifecycle:**
  - Issuance tracking (card number, issue date, issuer)
  - Expiry date management
  - Automatic renewal reminders (30/60/90 days)
  - Card status: `active`, `expired`, `lost`, `stolen`, `suspended`, `returned`
  - Photo documentation (card photo + employee photo)
  - Security features tracking (hologram, chip, etc.)
- **ID Card Types:**
  - Company ID cards
  - §34a GewO security ID (IHK-issued)
  - Client-specific access cards
  - Vehicle access cards
  - Building access cards
- **Loss/Theft Management:**
  - Immediate suspension capability
  - Report generation for authorities
  - Replacement process workflow
  - Cost tracking for replacements
  - Liability assignment (employee vs. company)
- **Return Management:**
  - Mandatory return upon termination
  - Return confirmation/receipt
  - Deactivation upon return
  - Destruction/archival process
- **Multi-Location:**
  - Cards issued at different locations
  - Location-specific access rights
  - Inter-location transfers
- **Compliance:**
  - All active employees have valid cards?
  - Expired cards report
  - Missing cards report
  - Audit trail of all card actions

**10. Employee Acknowledgment System:**

- **Clothing & Equipment Receipt:**
  - Digital signature for received items
  - List of all issued items
  - Condition documentation
  - Employee copy (PDF/Email)
- **Service ID Card Receipt:**
  - Acknowledgment of card issuance
  - Security responsibilities agreement
  - Loss/theft reporting obligations
  - Return obligations upon termination
- **Instructions & Policies Acknowledgment:**
  - **Work Instructions (Dienstanweisungen):**
    - Safety procedures
    - Emergency protocols
    - Client-specific instructions
    - Equipment usage guidelines
  - **Company Policies:**
    - Code of conduct
    - Confidentiality agreements
    - Data protection (GDPR training)
    - Workplace safety regulations
    - Anti-discrimination policies
  - **Acknowledgment Tracking:**
    - Which documents acknowledged by whom and when
    - Version control (new policy = new acknowledgment required)
    - Expiry/renewal (e.g., annual safety training acknowledgment)
    - Reminder system for overdue acknowledgments
    - Compliance reports (who hasn't acknowledged?)
  - **Delivery Methods:**
    - In-person with tablet/mobile signature
    - Email with click-to-acknowledge link
    - Portal with mandatory read-and-sign before access
    - Multi-language support for instructions
  - **Legal Validity:**
    - Timestamp and IP logging
    - Document version tracking
    - Immutable audit trail
    - PDF generation for records
    - Electronic signature compliance (eIDAS Textform §126b BGB)

**Technical Considerations:**

- Integrate with existing RBAC system
- Event sourcing for inventory changes? (audit trail)
- Barcode/QR code scanning for items and ID cards
- Mobile app support for field issuance
- Integration with laundry/cleaning services?
- Photo upload for condition documentation
- E-signature integration (DocuSign, Adobe Sign, or custom)
- Document versioning system
- Notification system (email, SMS, push notifications)

**Legal/Compliance:**

- Employee data privacy (size data is sensitive)
- Deposit regulations (Germany: Pfand-Regelungen)
- Tax implications of issued items (geldwerter Vorteil?)
- Liability for lost/damaged items
- ID card data protection (§34a data is sensitive)
- Electronic signature validity (§126b BGB - Textform)
- Document retention requirements (acknowledgments must be kept)
- GDPR compliance for acknowledgment tracking

**Related:**

- Employee Management (Core Feature)
- RBAC System (Core Feature)
- Multi-Branch Office Structure (if planned)
- Mobile Apps (ideas-backlog.md - for field issuance)
- Document Management System (for instructions/policies)
- BWR Integration (§34a ID cards)

**Estimated Development Effort:**

**MVP (Basic Inventory + Issuance):**

- Backend: 6-8 weeks (data model, business logic, permissions)
- Frontend: 4-6 weeks (inventory UI, issuance flows, reports)
- Testing & Refinement: 2-3 weeks
- **Total:** ~3-4 months for basic MVP

**Full Feature Set (with ID Cards, Acknowledgments, Multi-Supplier):**

- Backend: 12-16 weeks (extended data model, workflow logic, e-signatures)
- Frontend: 8-10 weeks (extended UI, acknowledgment flows, ID card management)
- Mobile App (optional): 6-8 weeks (field issuance, signature capture)
- Integration: 4-6 weeks (suppliers, e-signature providers, document management)
- Testing & Refinement: 4-6 weeks
- **Total:** ~6-9 months for full feature set

**Phased Approach Recommended:**

1. **Phase 1 (3-4 months):** Basic clothing inventory + issuance
2. **Phase 2 (2-3 months):** ID card management + basic acknowledgments
3. **Phase 3 (2-3 months):** Advanced features (multi-supplier, cost centers, full acknowledgment system)

---

**Next Actions:**

- Move Event Sourcing idea → ADR-001 ✅ Done
- Review this doc every 3 months
- Create GitHub Issues for "Now" or "Soon" priorities
- **NEW:** BWR-Integration → Move to feature-requirements.md (Soon)
- **NEW:** Clothing Management → Evaluate with stakeholders (Phase 3+)
