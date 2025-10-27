<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Feature Requirements & Business Logic

**Purpose:** Document business requirements and feature specifications for SecPal.

**Status:** Living document - Features move to GitHub Issues when prioritized

**Last Updated:** 2025-10-27

---

## 🔐 Access Control & Permissions (RBAC)

### Requirement: Flexible Role System

**Problem:**
Security companies have different organizational structures and job titles:

- "Objektleiter" vs. "Schichtleiter" vs. "Einsatzleiter"
- Flat organizations vs. deep hierarchies
- Different permission needs per client/location

**Requirements:**

1. **Predefined Roles (Templates):**

   - System Administrator (full access)
   - Company Manager (organization-wide access)
   - Operations Manager (shift planning, reporting)
   - Team Lead (shift supervision, limited admin)
   - Security Guard (field operations only)
   - Works Council / Betriebsrat (co-determination rights, audit access)
   - Client (read-only, restricted)

2. **Custom Roles:**

   - ✅ Users can create custom roles
   - ✅ Define permissions per role (granular)
   - ✅ Rename roles to match company terminology
   - ✅ Inherit from templates (e.g., "custom role based on Team Lead")

3. **Permission Granularity:**

   | Resource                | Create | Read | Update | Delete | Export |
   | ----------------------- | ------ | ---- | ------ | ------ | ------ |
   | Guard Book Entries      | ✓      | ✓    | ✗      | ✗      | ✓      |
   | Shifts                  | ✓      | ✓    | ✓      | ✓      | ✓      |
   | Employees               | ✓      | ✓    | ✓      | ✓      | ✗      |
   | Employee Qualifications | ✓      | ✓    | ✓      | ✓      | ✓      |
   | Clients                 | ✓      | ✓    | ✓      | ✓      | ✗      |
   | Reports                 | ✗      | ✓    | ✗      | ✗      | ✓      |
   | System Settings         | ✗      | ✓    | ✓      | ✗      | ✗      |

4. **Scope-Based Permissions:**
   - **Organization-wide:** Access all locations/clients
   - **Location-specific:** Only specific objects/sites
   - **Team-specific:** Only own team members
   - **Self-only:** Own data only (guards)

**Technical Implementation:**

```php
// app/Models/Role.php
class Role extends Model {
    protected $fillable = [
        'name',              // "Einsatzleiter", "Objektleiter", etc.
        'slug',              // "operations-manager"
        'is_system_role',    // Cannot be deleted
        'is_customizable',   // Can be edited by users
        'permissions',       // JSONB: ['guard_book.create', 'shifts.read', ...]
        'organization_id',   // Custom roles are org-specific
    ];

    protected $casts = [
        'permissions' => 'array',
    ];
}

// app/Policies/GuardBookEntryPolicy.php
class GuardBookEntryPolicy {
    public function viewAny(User $user): bool {
        return $user->hasPermission('guard_book.read');
    }

    public function create(User $user): bool {
        return $user->hasPermission('guard_book.create');
    }

    // Event sourcing: No update/delete allowed!
    public function update(User $user, GuardBookEntry $entry): bool {
        return false; // Immutable by design
    }
}
```

**Laravel Packages to Consider:**

- `spatie/laravel-permission` (popular, flexible)
- `silber/bouncer` (simpler)
- Custom implementation (more control)

**Priority:** 🔴 P0 (Blocker) - Required before multi-user testing

**Related:**

- Future ADR-004: RBAC Architecture
- Section below: Works Council (Betriebsrat) Permissions
- legal-compliance.md: GDPR access control requirements

---

## 🏛️ Works Council (Betriebsrat) Integration

### Requirement: Co-Determination Rights & Compliance

**Context:**

German labor law (BetrVG - Betriebsverfassungsgesetz) grants works councils (Betriebsrat) **co-determination rights** in various areas, including:

- Shift planning (§87 BetrVG)
- Working time arrangements
- Overtime distribution
- Employee data access (for performing their duties)

**Important:** Not all organizations have a works council (companies with ≥5 permanent employees can elect one), but **when present, their rights are legally binding**.

#### Works Council Hierarchies

**Complexity:** Organizations may have multi-level works council structures:

1. **Betriebsrat (BR)** - Works council for a single location/branch
2. **Spartenbetriebsrat** - Division-level works council (e.g., separate for different business units)
3. **Gesamtbetriebsrat (GBR)** - Central works council for entire company (when multiple locations exist)

**Hierarchy Rules:**

- **Higher councils override lower councils** on company-wide decisions
- **BUT:** Higher councils (GBR/Spartenbetriebsrat) have **NO authority** in operational areas like:
  - Individual shift planning for specific locations
  - Personnel matters of individual employees
  - Day-to-day operational decisions
- **Each BR retains authority** for their specific location/department

**Example Scenario:**

```
Company: SecureGuard GmbH (200+ employees, 5 branches)

Gesamtbetriebsrat (GBR)
  ├─ Can decide: Company-wide working time models
  ├─ Can decide: General overtime compensation rules
  └─ CANNOT decide: Berlin branch's November shift plan

Betriebsrat Berlin
  ├─ Can decide: Berlin location shift plans
  ├─ Can decide: Local overtime distribution
  └─ CANNOT override: Company-wide working time model set by GBR
```

**SecPal Approach:**

- ✅ Optional Betriebsrat role (can be disabled if no works council exists)
- ✅ Multi-level hierarchy support (BR → Spartenbetriebsrat → GBR)
- ✅ Configurable per organization/branch/division
- ✅ Scope-based permissions (GBR cannot approve local shift plans)
- ✅ Compliance workflows when enabled

### Features:

#### 1. Shift Plan Approval (Dienstplanausschuss)

**Workflow:**

```
Manager creates shift plan for next month
  ↓
System marks plan as "Pending BR Approval"
  ↓
BR receives notification
  ↓
BR reviews plan (reads all shifts, assignments)
  ↓
BR can:
  - ✅ Approve → Plan becomes "Active"
  - ❌ Reject → Plan blocked, manager must revise
  - 💬 Request Changes → Collaboration mode
  ↓
If approved: Shifts visible to employees
If rejected: Plan cannot be published
```

**Implementation:**

```php
Schema::create('shift_plans', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');
    $table->string('name'); // "November 2025"
    $table->date('period_start');
    $table->date('period_end');

    // Betriebsrat approval workflow
    $table->enum('br_status', [
        'draft',              // Not yet submitted to BR
        'pending_br',         // Awaiting BR review
        'br_approved',        // BR approved
        'br_rejected',        // BR rejected
        'br_not_required',    // No BR in this organization
    ])->default('draft');

    $table->foreignUuid('br_reviewed_by')->nullable(); // Which BR member
    $table->timestamp('br_reviewed_at')->nullable();
    $table->text('br_rejection_reason')->nullable();

    // Deadlines
    $table->timestamp('br_approval_deadline')->nullable(); // Must be approved by X

    $table->timestamps();
});
```

**Business Rules:**

```php
class ShiftPlanPolicy {
    public function publish(User $user, ShiftPlan $plan): bool {
        // Cannot publish without BR approval (if BR exists)
        if ($plan->organization->has_works_council) {
            return $plan->br_status === 'br_approved';
        }

        return $user->hasPermission('shift_plans.publish');
    }

    public function approve(User $user, ShiftPlan $plan): bool {
        return $user->hasRole('works_council')
            && $plan->br_status === 'pending_br';
    }
}
```

#### 2. Approval Deadlines

**Configuration:**

```php
// Organization settings
$organization->settings = [
    'works_council' => [
        'enabled' => true,
        'approval_required_for' => ['shift_plans', 'overtime_rules'],
        'approval_deadline_days' => 14, // BR must approve 14 days before period start
        'auto_reject_on_deadline' => false, // Or auto-approve?
    ],
];
```

**Deadline Alerts:**

```php
// app/Console/Commands/CheckBRApprovalDeadlines.php
class CheckBRApprovalDeadlines extends Command {
    public function handle() {
        $approaching = ShiftPlan::where('br_status', 'pending_br')
            ->whereBetween('br_approval_deadline', [
                now(),
                now()->addDays(3),
            ])
            ->get();

        foreach ($approaching as $plan) {
            Notification::send(
                $plan->organization->worksCouncilMembers,
                new BRApprovalDeadlineApproaching($plan)
            );
        }
    }
}
```

#### 3. Employee File Access (Mitarbeiterdaten)

**Context:**

Works councils have the right to access employee data **when necessary for performing their duties** (§99 BetrVG).

**SecPal Implementation:**

**Option A: Permanent Access**

```php
class EmployeePolicy {
    public function viewAny(User $user): bool {
        return $user->hasRole('works_council')
            || $user->hasPermission('employees.read');
    }
}
```

**Option B: Request-Based Access (More Privacy-Friendly)**

```php
Schema::create('br_data_access_requests', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('requester_id'); // BR member
    $table->foreignUuid('employee_id')->nullable(); // Specific employee or null for all
    $table->enum('request_type', ['employee_file', 'shift_history', 'time_records']);
    $table->text('justification'); // "Prüfung Überstundenvergütung"
    $table->enum('status', ['pending', 'approved', 'rejected']);
    $table->foreignUuid('approved_by')->nullable(); // Manager/Admin
    $table->timestamp('approved_at')->nullable();
    $table->timestamp('access_expires_at')->nullable(); // Temporary access
    $table->timestamps();
});
```

**Workflow:**

```
BR member requests access to employee file
  ↓
Justification required: "Warum benötigt?"
  ↓
Manager/Admin reviews request
  ↓
If approved: Temporary access granted (e.g., 7 days)
  ↓
All BR access logged (audit trail)
```

#### 4. Access Logging (Zugriffsprotokolle)

**Legal Requirement:**

When works councils access employee data, this must be logged (transparency, data protection).

```php
Schema::create('br_access_logs', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('br_member_id');
    $table->foreignUuid('accessed_employee_id')->nullable();
    $table->string('action'); // 'viewed_employee_file', 'exported_shift_plan'
    $table->jsonb('metadata'); // What exactly was accessed
    $table->timestamp('accessed_at');
    $table->string('ip_address', 45);
    $table->text('user_agent');
});

// Automatic logging via middleware
class LogBRAccess {
    public function handle(Request $request, Closure $next) {
        if ($request->user()->hasRole('works_council')) {
            BRAccessLog::create([
                'br_member_id' => $request->user()->id,
                'action' => $request->route()->getName(),
                'accessed_at' => now(),
                'ip_address' => $request->ip(),
                'user_agent' => $request->userAgent(),
            ]);
        }

        return $next($request);
    }
}
```

**Access Log Export:**

Managers/Admins can export BR access logs (for compliance audits).

#### 5. Co-Determination Workflows

**Example: Overtime Rules**

```
Manager wants to change overtime compensation rules
  ↓
System requires BR approval (§87 BetrVG)
  ↓
BR reviews proposal
  ↓
BR approves/rejects
  ↓
If approved: Rules take effect
If rejected: Rules blocked
```

**Implementation:**

```php
Schema::create('br_approval_workflows', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');
    $table->string('subject_type'); // 'ShiftPlan', 'OvertimeRule', 'WorkingTimeModel'
    $table->uuid('subject_id');
    $table->enum('status', ['pending_br', 'br_approved', 'br_rejected']);
    $table->text('br_comments')->nullable();
    $table->timestamps();
});
```

### Works Council Dashboard

**BR Members see:**

```
┌─────────────────────────────────────────────────────┐
│ Betriebsrat Dashboard                               │
├─────────────────────────────────────────────────────┤
│ Offene Freigaben (3):                               │
│                                                     │
│ 🕐 Dienstplan Dezember 2025                        │
│    Deadline: 15.11.2025                             │
│    [Prüfen] [Freigeben] [Ablehnen]                 │
│                                                     │
│ 🕐 Überstundenregelung Änderung                    │
│    Deadline: 01.11.2025                             │
│    [Prüfen] [Freigeben] [Ablehnen]                 │
│                                                     │
│ Zugriffsprotokolle (letzte 30 Tage):               │
│    27.10.2025 - Mitarbeiterakte Max M. eingesehen  │
│    25.10.2025 - Dienstplan Oktober exportiert      │
│                                                     │
│ [Datenzugriff beantragen]                          │
└─────────────────────────────────────────────────────┘
```

### Works Council Permissions Matrix

| Resource         | Read | Approve | Reject | Export | Comment |
| ---------------- | ---- | ------- | ------ | ------ | ------- |
| Shift Plans      | ✅   | ✅      | ✅     | ✅     | ✅      |
| Employee Files   | 🔐\* | ❌      | ❌     | 🔐\*   | ❌      |
| Working Time     | ✅   | ✅      | ✅     | ✅     | ✅      |
| Overtime Records | ✅   | ❌      | ❌     | ✅     | ❌      |
| Guard Book       | ❌   | ❌      | ❌     | ❌     | ❌      |
| System Settings  | ❌   | ❌      | ❌     | ❌     | ❌      |

_\* 🔐 = Request-based access with justification required_

### Configuration

**Enable/Disable per Organization:**

```php
// Database migration
Schema::table('organizations', function (Blueprint $table) {
    $table->boolean('has_works_council')->default(false);
    $table->jsonb('works_council_settings')->nullable();
});

// Settings example
{
    "enabled": true,
    "approval_required": {
        "shift_plans": true,
        "overtime_rules": true,
        "working_time_models": true
    },
    "approval_deadline_days": 14,
    "data_access_model": "request_based", // or "permanent"
    "access_log_retention_days": 365
}
```

### Multi-Level Works Council Hierarchy

**Database Schema for Hierarchy Support:**

```php
Schema::create('works_councils', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');

    // Hierarchy
    $table->enum('level', [
        'betriebsrat',           // Single location/branch
        'spartenbetriebsrat',    // Division-level
        'gesamtbetriebsrat'      // Central/company-wide
    ]);

    $table->string('name'); // "BR Berlin", "GBR Deutschland", "Sparten-BR Sicherheit"

    // Scope: Which locations/divisions does this council cover?
    $table->foreignUuid('branch_id')->nullable(); // For BR (specific branch)
    $table->foreignUuid('division_id')->nullable(); // For Spartenbetriebsrat
    $table->boolean('is_company_wide')->default(false); // For GBR

    // Parent relationship (BR → Spartenbetriebsrat → GBR)
    $table->foreignUuid('parent_council_id')->nullable();

    // Authority scope
    $table->jsonb('authority_scope')->nullable(); // What can this council approve?

    $table->timestamps();
});

Schema::create('works_council_members', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('works_council_id');
    $table->foreignUuid('employee_id'); // Member is also an employee
    $table->enum('role', ['member', 'chairperson', 'deputy_chairperson']);
    $table->date('term_start');
    $table->date('term_end')->nullable(); // Typically 4 years (BetrVG §21)
    $table->timestamps();
});

// Link users to works council roles
Schema::table('users', function (Blueprint $table) {
    $table->foreignUuid('works_council_id')->nullable();
    $table->boolean('is_works_council_member')->default(false);
});
```

**Authority Scope Configuration:**

```php
// Example: Gesamtbetriebsrat (company-wide decisions only)
{
    "can_approve": [
        "working_time_models",      // §87 BetrVG
        "overtime_compensation",    // §87 BetrVG
        "company_wide_policies"
    ],
    "cannot_approve": [
        "shift_plans",              // ← Local BR responsibility
        "individual_employee_matters"
    ],
    "scope": "all_branches"
}

// Example: Betriebsrat Berlin (local decisions)
{
    "can_approve": [
        "shift_plans",
        "local_overtime_distribution",
        "vacation_planning"
    ],
    "scope": "branch_berlin"
}
```

**Business Logic: Authority Validation**

```php
class WorksCouncilPolicy {
    public function canApprove(User $user, ShiftPlan $plan): bool {
        $council = $user->worksCouncil;

        // GBR cannot approve location-specific shift plans
        if ($council->level === 'gesamtbetriebsrat') {
            return false; // No authority for local shift plans
        }

        // Spartenbetriebsrat can only approve if division matches
        if ($council->level === 'spartenbetriebsrat') {
            return $plan->branch->division_id === $council->division_id;
        }

        // Betriebsrat can only approve if branch matches
        if ($council->level === 'betriebsrat') {
            return $plan->branch_id === $council->branch_id;
        }

        return false;
    }
}
```

**UI: Branch/Council Selection**

```
┌─────────────────────────────────────────────────────┐
│ Dienstplan erstellen                                │
├─────────────────────────────────────────────────────┤
│ Standort: [Berlin Mitte ▼]                         │
│                                                     │
│ → Zuständiger Betriebsrat: BR Berlin               │
│   (Freigabe erforderlich)                          │
│                                                     │
│ → Übergeordnet: Sparten-BR Sicherheit              │
│   (keine Freigabe für Dienstpläne)                 │
│                                                     │
│ → Übergeordnet: GBR SecureGuard GmbH               │
│   (keine Freigabe für Dienstpläne)                 │
└─────────────────────────────────────────────────────┘
```

**Priority:** 🔴 P0 (Blocker if targeting German market)

**Legal Risk:** 🟡 Medium (requires correct implementation of BetrVG)

**Related:**

- legal-compliance.md: BetrVG compliance
- Future: Betriebsrat training documentation

---

## 👥 Employee Management (HR Module)

### Requirement: Comprehensive Employee Records

**Context:**
Security companies need employee data for:

- Legal compliance (BewachV §34a: Qualification proof)
- Shift planning (availability, qualifications)
- Contract management (employment status, working hours)
- Training management (course expiry dates)

**Features:**

### 1. Employee Profile

**Data Fields:**

```yaml
Personal Information:
  - Employee Number: (unique, auto-generated or manual)
  - First Name: (required)
  - Last Name: (required)
  - Date of Birth: (for age-restricted assignments)
  - Photo: (for ID badge, optional)
  - Contact Email: (for app login)
  - Phone Number: (emergency contact)
  - Address: (for travel distance calculation)

Employment Details:
  - Employment Status: [Active, Inactive, On Leave, Terminated]
  - Contract Type: [Full-time, Part-time, Minijob, Freelance]
  - Hire Date: (required)
  - Termination Date: (if applicable)
  - Weekly Working Hours: (for contract compliance)
  - Hourly Rate / Salary: (for cost calculation, restricted access)

Legal Requirements:
  - §34a Certificate Number: (Sachkundeprüfung)
  - §34a Expiry Date: (if temporary)
  - Work Permit: (for non-EU employees)
  - Criminal Record Check: [Valid, Expired, Pending]
  - Criminal Record Check Date: (refresh every 5 years)

System Access:
  - User Account: (linked to authentication)
  - Assigned Roles: (RBAC roles)
  - Mobile App Access: [Enabled, Disabled]
  - Last Login: (tracking)
```

**Data Protection:**

- ✅ Separate personal data from operational data
- ✅ Encrypt salary information
- ✅ Clients cannot see employee names (pseudonymize: "Guard #1234")
- ✅ Managers only see employees in their teams (scope-based)

**Implementation:**

```php
Schema::create('employees', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->uuid('organization_id');
    $table->string('employee_number')->unique();

    // Personal (encrypted)
    $table->text('first_name_encrypted');
    $table->text('last_name_encrypted');
    $table->date('date_of_birth_encrypted')->nullable();

    // Employment
    $table->enum('status', ['active', 'inactive', 'on_leave', 'terminated']);
    $table->enum('contract_type', ['full_time', 'part_time', 'minijob', 'freelance']);
    $table->date('hire_date');
    $table->date('termination_date')->nullable();
    $table->decimal('weekly_hours', 5, 2)->nullable();

    // Legal (BewachV)
    $table->string('sachkunde_certificate')->nullable();
    $table->date('sachkunde_expiry')->nullable();
    $table->date('criminal_record_check_date')->nullable();

    // System
    $table->foreignUuid('user_id')->nullable(); // Link to auth user

    $table->timestamps();
    $table->softDeletes();
});
```

**Priority:** 🔴 P0 (Blocker) - Core feature

---

## 🎓 Qualification Management

### Requirement: Track Training & Certifications

**Context:**
Security guards require various qualifications according to §34a GewO (Gewerbeordnung):

- **Mandatory (for certain activities):**
  - §34a Sachkundeunterrichtung (40-hour training course)
  - §34a Sachkundeprüfung (IHK examination, more comprehensive)
- **Advanced Certifications:**
  - Geprüfte Schutz- und Sicherheitskraft (GSSK) - IHK certified specialist
  - Servicekraft für Schutz und Sicherheit - Basic IHK certification
  - Fachkraft für Schutz und Sicherheit - Advanced IHK certification
  - Meister für Schutz und Sicherheit - Master craftsman level
- **Additional Qualifications:**
  - First aid (Erste Hilfe)
  - Fire safety (Brandschutzhelfer)
  - Specialized skills (weapons, dogs, etc.)
- **Recurring:** Many qualifications require periodic renewal

**Features:**

### 1. Qualification Types

**Predefined Qualifications (§34a GewO):**

- **§34a Sachkundeunterrichtung** (40h training, no exam)
- **§34a Sachkundeprüfung** (IHK exam, higher qualification)
- **Geprüfte Schutz- und Sicherheitskraft (GSSK)** - IHK specialist
- **Servicekraft für Schutz und Sicherheit** - IHK basic
- **Fachkraft für Schutz und Sicherheit** - IHK advanced
- **Meister für Schutz und Sicherheit** - Master level

**Additional Predefined Qualifications:**

- First Aid (Erste Hilfe) - Renewal: 2 years
- Fire Safety Officer (Brandschutzhelfer) - Renewal: 3-5 years
- Safety Officer (Sicherheitsbeauftragter)
- Dog Handler (Hundeführer)
- Weapons License (Waffenschein) - Various types
- Intervention Services (Interventionsdienst)

**Custom Qualifications:**

- ✅ Add organization-specific qualifications
- ✅ Define if mandatory or optional
- ✅ Set renewal period (e.g., every 2 years)
- ✅ Define prerequisites (e.g., "Meister requires Fachkraft")

### 2. Employee Qualifications

**Data Model:**

```php
Schema::create('qualifications', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->uuid('organization_id');
    $table->string('name'); // "Erste Hilfe", "Brandschutzhelfer"
    $table->text('description')->nullable();
    $table->boolean('is_mandatory')->default(false);
    $table->integer('renewal_period_months')->nullable(); // 24 for first aid
    $table->boolean('is_system_qualification')->default(false);
    $table->timestamps();
});

Schema::create('employee_qualifications', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('employee_id');
    $table->foreignUuid('qualification_id');

    $table->date('obtained_date');
    $table->date('expiry_date')->nullable();
    $table->string('certificate_number')->nullable();
    $table->string('issuing_authority')->nullable(); // "IHK Berlin", "DRK"
    $table->text('notes')->nullable();

    // Document storage
    $table->string('certificate_file_path')->nullable(); // PDF scan

    $table->enum('status', ['valid', 'expiring_soon', 'expired']);
    $table->timestamps();
});
```

### 3. Expiry Alerts

**Automated Notifications:**

```php
// app/Console/Commands/CheckQualificationExpiry.php
class CheckQualificationExpiry extends Command {
    public function handle() {
        $expiringIn30Days = EmployeeQualification::whereBetween('expiry_date', [
            now(),
            now()->addDays(30),
        ])->get();

        foreach ($expiringIn30Days as $qual) {
            Notification::send(
                [$qual->employee->manager, $qual->employee],
                new QualificationExpiringNotification($qual)
            );
        }

        // Update status
        $qual->update(['status' => 'expiring_soon']);
    }
}
```

**Dashboard Widgets:**

- "Qualifications expiring this month" (sortable by date)
- "Employees missing mandatory qualifications"
- "Upcoming group trainings" (coordinate renewals)

### 4. Group Training Planner

**Feature:** Schedule group courses when multiple employees need renewal

**Logic:**

1. Find all employees with qualification expiring in next 3 months
2. Group by qualification type
3. Suggest training dates when ≥5 employees need same course
4. Book training with external provider or internal trainer

**UI:**

```
┌─────────────────────────────────────────────────────┐
│ Group Training Suggestions                          │
├─────────────────────────────────────────────────────┤
│ Erste Hilfe Kurs                                    │
│ 12 Mitarbeiter benötigen Auffrischung               │
│ Ablaufdaten: 15.11.2025 - 20.02.2026               │
│                                                     │
│ [Gruppenschulung planen] [Details ansehen]         │
└─────────────────────────────────────────────────────┘
```

**Priority:** 🟠 P1 (High) - Competitive differentiator

---

## ✍️ Digital Signatures & Acknowledgments

### Requirement: Legally-Binding Digital Confirmations

**Context:**

Security companies need documented proof of various employee acknowledgments and handovers:

- **Equipment Handovers:** Uniforms, keys, radios, phones, ID badges
- **Work Instruction Acknowledgment:** Employee confirms reading and understanding
- **Policy Acknowledgment:** Data protection, code of conduct, safety policies
- **Document Receipt:** Contract, payslips, certificates
- **Training Attendance:** Confirmation of participation
- **Incident Reports:** Witness signatures

**Legal Requirements:**

- ✅ Identity verification (link to employee account)
- ✅ Timestamp (when was it signed?)
- ✅ Non-repudiation (cannot deny signing)
- ✅ Tamper-proof (cannot be altered after signing)
- ✅ Audit trail (OpenTimestamp integration)

### Features:

#### 1. Digital Signature Capture

**Technologies:**

**Option A: Canvas-Based Signature (Mobile/Tablet)**

```typescript
// Signature pad component (React)
import SignatureCanvas from "react-signature-canvas";

const DigitalSignaturePad: React.FC<Props> = ({ onSign }) => {
  const sigCanvas = useRef<SignatureCanvas>(null);

  const handleSign = () => {
    if (sigCanvas.current) {
      const dataURL = sigCanvas.current.toDataURL(); // Base64 PNG
      onSign(dataURL);
    }
  };

  return (
    <div className="signature-container">
      <SignatureCanvas
        ref={sigCanvas}
        canvasProps={{
          width: 400,
          height: 200,
          className: "signature-canvas",
        }}
      />
      <button onClick={() => sigCanvas.current?.clear()}>Löschen</button>
      <button onClick={handleSign}>Unterschrift speichern</button>
    </div>
  );
};
```

**Option B: Account-Linked Digital Acceptance (No Drawing)**

```typescript
// Simple checkbox confirmation linked to account
const AccountLinkedAcknowledgment: React.FC<Props> = ({ documentId, employeeId }) => {
  const handleAcknowledge = async () => {
    // User must be authenticated
    await api.post("/acknowledgments", {
      document_id: documentId,
      employee_id: employeeId,
      acknowledged_at: new Date(),
      ip_address: clientIP,
      device_fingerprint: deviceFingerprint,
      // No visual signature, but legally binding via account link
    });
  };

  return (
    <div className="acknowledgment">
      <input type="checkbox" id="acknowledge" onChange={handleAcknowledge} />
      <label htmlFor="acknowledge">
        Ich bestätige, dass ich dieses Dokument gelesen und verstanden habe.
      </label>
      <p className="text-muted">
        Ihre Bestätigung wird mit Ihrer Identität verknüpft und ist rechtlich bindend.
      </p>
    </div>
  );
};
```

**Recommended Hybrid Approach:**

- **Equipment handovers:** Visual signature on touchscreen (feels more official)
- **Document acknowledgments:** Account-linked checkbox (faster, equally valid)

#### 2. Database Schema

```php
Schema::create('digital_signatures', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');

    // Who signed?
    $table->foreignUuid('employee_id');
    $table->foreignUuid('user_id'); // Account that was logged in

    // What was signed?
    $table->enum('signature_type', [
        'equipment_handover',
        'work_instruction_acknowledgment',
        'policy_acknowledgment',
        'document_receipt',
        'training_attendance',
        'incident_witness',
        'custom'
    ]);

    $table->foreignUuid('related_document_id')->nullable(); // Links to work_instructions, etc.
    $table->string('related_document_type')->nullable(); // Polymorphic

    // Signature data
    $table->text('signature_image_base64')->nullable(); // Visual signature (if used)
    $table->boolean('is_visual_signature')->default(false);

    // Tamper-proofing
    $table->timestamp('signed_at');
    $table->string('signature_hash', 64); // SHA-256 of signature data + metadata
    $table->string('opentimestamp_proof')->nullable(); // OTS proof file

    // Context (forensics)
    $table->string('ip_address')->nullable();
    $table->string('device_fingerprint')->nullable();
    $table->string('geolocation')->nullable(); // Optional GPS coordinates

    // Witness (optional, for critical signatures)
    $table->foreignUuid('witness_user_id')->nullable();
    $table->timestamp('witness_signed_at')->nullable();

    $table->timestamps();
});
```

#### 3. Use Case: Equipment Handover

**Workflow:**

```
1. Manager creates equipment handover record
   → Items: 2x Uniform, 1x Radio, 1x Flashlight, 1x ID Badge

2. Employee receives items

3. Employee signs on tablet/phone:
   - Visual signature OR account-linked checkbox
   - Optional: Photo of received items

4. System records:
   - Timestamp
   - Employee ID (from login)
   - IP address, device
   - Creates SHA-256 hash of all data
   - Submits to OpenTimestamp (blockchain proof)

5. Both parties receive email confirmation with PDF
```

**Implementation:**

```php
Schema::create('equipment_handovers', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');
    $table->foreignUuid('employee_id');
    $table->foreignUuid('issued_by_user_id'); // Manager who handed over

    $table->jsonb('items'); // ["Uniform (2x)", "Radio Motorola XPR7550", ...]
    $table->text('notes')->nullable();

    $table->enum('handover_type', ['issue', 'return', 'exchange']);
    $table->timestamp('handover_date');

    // Signature link
    $table->foreignUuid('employee_signature_id')->nullable();
    $table->foreignUuid('issuer_signature_id')->nullable();

    $table->enum('status', ['pending', 'signed', 'returned']);
    $table->timestamps();
});

// Service class
class EquipmentHandoverService {
    public function createHandover(array $data): EquipmentHandover {
        return DB::transaction(function () use ($data) {
            $handover = EquipmentHandover::create($data);

            // Generate PDF
            $pdf = $this->generateHandoverPDF($handover);

            // Notify employee
            Notification::send(
                $handover->employee,
                new EquipmentHandoverPending($handover)
            );

            return $handover;
        });
    }

    public function recordSignature(
        EquipmentHandover $handover,
        User $user,
        ?string $signatureData
    ): DigitalSignature {
        $signature = DigitalSignature::create([
            'employee_id' => $user->employee_id,
            'user_id' => $user->id,
            'signature_type' => 'equipment_handover',
            'related_document_id' => $handover->id,
            'related_document_type' => EquipmentHandover::class,
            'signature_image_base64' => $signatureData,
            'is_visual_signature' => !is_null($signatureData),
            'signed_at' => now(),
            'signature_hash' => $this->generateSignatureHash($handover, $user),
            'ip_address' => request()->ip(),
            'device_fingerprint' => $this->getDeviceFingerprint(),
        ]);

        // Update handover
        $handover->update([
            'employee_signature_id' => $signature->id,
            'status' => 'signed',
        ]);

        // Submit to OpenTimestamp (background job)
        SubmitToOpenTimestamp::dispatch($signature);

        // Email confirmation
        Mail::to($handover->employee->email)->send(
            new EquipmentHandoverConfirmation($handover, $signature)
        );

        return $signature;
    }

    private function generateSignatureHash(
        EquipmentHandover $handover,
        User $user
    ): string {
        $data = json_encode([
            'handover_id' => $handover->id,
            'employee_id' => $user->employee_id,
            'items' => $handover->items,
            'timestamp' => now()->toIso8601String(),
        ]);

        return hash('sha256', $data);
    }
}
```

#### 4. PDF Generation with Signature

```php
use Barryvdh\DomPDF\Facade\Pdf;

class HandoverPDFGenerator {
    public function generate(EquipmentHandover $handover): string {
        $data = [
            'handover' => $handover,
            'signature' => $handover->employeeSignature,
            'timestamp_proof' => $handover->employeeSignature?->opentimestamp_proof,
        ];

        $pdf = Pdf::loadView('pdfs.equipment_handover', $data);

        $path = storage_path("app/handovers/{$handover->id}.pdf");
        $pdf->save($path);

        return $path;
    }
}
```

**PDF Template Example:**

```blade
{{-- resources/views/pdfs/equipment_handover.blade.php --}}
<!DOCTYPE html>
<html>
<head>
    <title>Ausgabequittung</title>
    <style>
        body { font-family: Arial, sans-serif; }
        .signature-box { border: 1px solid #ccc; padding: 20px; margin-top: 20px; }
        .signature-image { max-width: 300px; }
    </style>
</head>
<body>
    <h1>Ausgabequittung</h1>

    <p><strong>Mitarbeiter:</strong> {{ $handover->employee->full_name }}</p>
    <p><strong>Datum:</strong> {{ $handover->handover_date->format('d.m.Y H:i') }}</p>
    <p><strong>Ausgegeben von:</strong> {{ $handover->issuedBy->name }}</p>

    <h2>Ausgegebene Gegenstände:</h2>
    <ul>
        @foreach($handover->items as $item)
            <li>{{ $item }}</li>
        @endforeach
    </ul>

    @if($signature)
        <div class="signature-box">
            <h3>Digitale Unterschrift</h3>

            @if($signature->is_visual_signature)
                <img src="{{ $signature->signature_image_base64 }}"
                     alt="Unterschrift"
                     class="signature-image">
            @else
                <p>✓ Bestätigt via Account-Login am {{ $signature->signed_at->format('d.m.Y H:i:s') }}</p>
            @endif

            <p><strong>Signatur-Hash:</strong> <code>{{ $signature->signature_hash }}</code></p>
            <p><strong>IP-Adresse:</strong> {{ $signature->ip_address }}</p>

            @if($timestamp_proof)
                <p><strong>OpenTimestamp-Nachweis:</strong> Verifiziert via Bitcoin-Blockchain</p>
                <small>OTS-Datei verfügbar für unabhängige Verifikation</small>
            @endif
        </div>
    @endif

    <p style="margin-top: 40px; font-size: 10px; color: #666;">
        Dieses Dokument wurde digital erstellt und signiert. Die Integrität kann über den
        Signatur-Hash und OpenTimestamp-Nachweis verifiziert werden.
    </p>
</body>
</html>
```

#### 5. Verification & Audit Trail

```php
class SignatureVerificationService {
    public function verify(DigitalSignature $signature): array {
        $results = [];

        // 1. Check hash integrity
        $currentHash = $this->recalculateHash($signature);
        $results['hash_valid'] = $currentHash === $signature->signature_hash;

        // 2. Check OpenTimestamp proof (if available)
        if ($signature->opentimestamp_proof) {
            $results['timestamp_valid'] = $this->verifyOpenTimestamp(
                $signature->signature_hash,
                $signature->opentimestamp_proof
            );
        }

        // 3. Check user account validity at time of signing
        $results['user_existed'] = User::withTrashed()
            ->where('id', $signature->user_id)
            ->where('created_at', '<=', $signature->signed_at)
            ->exists();

        return $results;
    }
}
```

**Priority:** 🟠 P1 (High) - Legal compliance + efficiency

**Legal Risk:** 🟡 Medium (requires correct implementation for legal validity)

---

## 📋 Work Instructions Management (Dienstanweisungen)

### Requirement: Centralized Work Instruction System with Mandatory Acknowledgment

**Context:**

Security companies must issue **work instructions (Dienstanweisungen)** to employees for:

- Site-specific procedures (client locations)
- General operating procedures (company-wide)
- Safety protocols (emergency procedures)
- Quality standards (DIN 77200 compliance)
- Legal requirements (data protection, BewachV)

**Challenges:**

- ❌ Paper-based instructions get lost
- ❌ No proof of employee acknowledgment
- ❌ Difficult to update (must reprint and redistribute)
- ❌ No version control (which version did employee read?)
- ❌ Time-consuming to create from scratch

**SecPal Solution: Digital Work Instruction Configurator**

### Features:

#### 1. Work Instruction Builder

**Template Library:**

- ✅ Pre-built templates for common scenarios
- ✅ Standard text blocks (legal boilerplate)
- ✅ Customizable templates (organization-specific)
- ✅ Client-specific templates (location procedures)

**Template Categories:**

```yaml
Allgemeine Dienstanweisungen (General Instructions):
  - Verhaltenskodex (Code of Conduct)
  - Datenschutz-Richtlinie (Data Protection)
  - Meldepflichten (Reporting Obligations)
  - Notfallprozeduren (Emergency Procedures)

Objektbezogene Dienstanweisungen (Site-Specific):
  - Zugangskontrollen (Access Control)
  - Rundgangspläne (Patrol Routes)
  - Besondere Gefahren (Specific Hazards)
  - Ansprechpartner Objekt (Client Contacts)

Sicherheitstechnische Anweisungen (Safety):
  - Brandschutz (Fire Safety)
  - Erste Hilfe (First Aid)
  - Evakuierung (Evacuation)
  - Gefahrstoffumgang (Hazardous Materials)
```

**Database Schema:**

```php
Schema::create('work_instruction_templates', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id')->nullable(); // Null = system template

    $table->string('name'); // "Verhaltenskodex", "Zugangskontr olle Vorlage"
    $table->string('category'); // "general", "site_specific", "safety"
    $table->text('description')->nullable();

    // Template structure (JSON)
    $table->jsonb('sections'); // Array of editable sections
    $table->jsonb('standard_blocks'); // Pre-filled text blocks

    $table->boolean('is_system_template')->default(false); // Can't be deleted
    $table->boolean('is_active')->default(true);

    $table->timestamps();
});

Schema::create('work_instructions', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');
    $table->foreignUuid('template_id')->nullable(); // If created from template

    $table->string('title'); // "Dienstanweisung Objekt A"
    $table->string('instruction_number')->unique(); // "DA-2025-001"
    $table->integer('version')->default(1); // Version control

    // Content
    $table->jsonb('content'); // Structured content (sections, paragraphs)
    $table->text('content_html'); // Rendered HTML for display
    $table->text('content_pdf_path')->nullable(); // Generated PDF

    // Metadata
    $table->foreignUuid('created_by_user_id');
    $table->date('valid_from');
    $table->date('valid_until')->nullable();
    $table->enum('status', ['draft', 'review', 'published', 'archived']);

    // Acknowledgment requirements
    $table->boolean('requires_acknowledgment')->default(true);
    $table->integer('acknowledgment_deadline_days')->default(7); // Must ack within 7 days

    // Scope: Who must read this?
    $table->enum('scope', ['all_employees', 'specific_employees', 'by_role', 'by_location']);
    $table->jsonb('scope_criteria')->nullable(); // Employee IDs, roles, or location IDs

    $table->timestamps();
    $table->softDeletes();
});

Schema::create('work_instruction_acknowledgments', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('work_instruction_id');
    $table->foreignUuid('employee_id');

    // Digital signature link
    $table->foreignUuid('signature_id'); // Links to digital_signatures table

    $table->timestamp('acknowledged_at');
    $table->timestamp('deadline')->nullable(); // When must it be acknowledged?
    $table->boolean('is_overdue')->default(false);

    // Quiz/Test (optional)
    $table->jsonb('quiz_answers')->nullable(); // If instruction has comprehension test
    $table->integer('quiz_score')->nullable();
    $table->boolean('quiz_passed')->nullable();

    $table->timestamps();

    $table->unique(['work_instruction_id', 'employee_id']); // One ack per employee
});
```

#### 2. Instruction Builder UI

**Drag & Drop Interface:**

```typescript
// React component structure
const WorkInstructionBuilder: React.FC = () => {
  const [sections, setSections] = useState<Section[]>([]);

  const addSection = (type: "heading" | "paragraph" | "list" | "standard_block") => {
    // Add new editable section
  };

  const insertStandardBlock = (blockId: string) => {
    // Insert pre-written legal/standard text
  };

  return (
    <div className="instruction-builder">
      <div className="sidebar">
        <h3>Vorlagen</h3>
        <TemplateList onSelect={loadTemplate} />

        <h3>Standardbausteine</h3>
        <StandardBlockList onSelect={insertStandardBlock} />
      </div>

      <div className="editor">
        <input
          type="text"
          placeholder="Titel der Dienstanweisung"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="sections">
            {(provided) => (
              <div {...provided.droppableProps} ref={provided.innerRef}>
                {sections.map((section, index) => (
                  <Draggable key={section.id} draggableId={section.id} index={index}>
                    {(provided) => (
                      <SectionEditor
                        section={section}
                        ref={provided.innerRef}
                        {...provided.draggableProps}
                        {...provided.dragHandleProps}
                      />
                    )}
                  </Draggable>
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>

        <button onClick={() => addSection("paragraph")}>+ Absatz</button>
        <button onClick={() => addSection("list")}>+ Liste</button>
        <button onClick={() => addSection("standard_block")}>+ Standardbaustein</button>
      </div>

      <div className="preview">
        <h3>Vorschau</h3>
        <InstructionPreview content={sections} />
      </div>
    </div>
  );
};
```

**Standard Blocks Example:**

```json
{
  "id": "std_datenschutz_basic",
  "name": "Datenschutz-Grundsatz",
  "category": "legal",
  "locked": true,
  "content": {
    "de": "Alle Mitarbeiter sind zur Einhaltung der Datenschutz-Grundverordnung (DSGVO) verpflichtet. Personenbezogene Daten dürfen nur im Rahmen der dienstlichen Tätigkeit erhoben und verarbeitet werden. Eine Weitergabe an Dritte ist untersagt, sofern keine rechtliche Grundlage besteht."
  }
}
```

#### 3. Forced Acknowledgment Workflow

**Process:**

```
1. Manager creates work instruction
   ↓
2. Manager publishes instruction
   ↓
3. System determines target employees (based on scope)
   ↓
4. System creates acknowledgment tasks for each employee
   ↓
5. Employees receive:
   - Email notification
   - Mobile app notification
   - Dashboard alert (cannot be dismissed)
   ↓
6. Employee must:
   - Read instruction (scroll to bottom detection)
   - Optional: Complete comprehension quiz
   - Click "Ich habe verstanden" (Digital signature created)
   ↓
7. If not acknowledged by deadline:
   - Daily reminder emails
   - Escalation to manager
   - Optional: Block shift assignments until acknowledged
```

**Implementation:**

```php
// app/Services/WorkInstructionPublisher.php
class WorkInstructionPublisher {
    public function publish(WorkInstruction $instruction): void {
        DB::transaction(function () use ($instruction) {
            // Update status
            $instruction->update(['status' => 'published']);

            // Determine target employees
            $employees = $this->getTargetEmployees($instruction);

            // Create acknowledgment tasks
            foreach ($employees as $employee) {
                $deadline = now()->addDays($instruction->acknowledgment_deadline_days);

                WorkInstructionAcknowledgment::create([
                    'work_instruction_id' => $instruction->id,
                    'employee_id' => $employee->id,
                    'deadline' => $deadline,
                ]);

                // Notify employee
                Notification::send($employee,
                    new NewWorkInstructionNotification($instruction, $deadline)
                );
            }

            // Event for audit log
            event(new WorkInstructionPublished($instruction, $employees->count()));
        });
    }

    private function getTargetEmployees(WorkInstruction $instruction): Collection {
        return match($instruction->scope) {
            'all_employees' => Employee::where('status', 'active')->get(),
            'specific_employees' => Employee::whereIn('id', $instruction->scope_criteria)->get(),
            'by_role' => Employee::whereHas('user', function ($q) use ($instruction) {
                $q->whereHas('roles', function ($q2) use ($instruction) {
                    $q2->whereIn('name', $instruction->scope_criteria);
                });
            })->get(),
            'by_location' => Employee::whereIn('primary_location_id', $instruction->scope_criteria)->get(),
        };
    }
}

// app/Console/Commands/CheckOverdueAcknowledgments.php
class CheckOverdueAcknowledgments extends Command {
    public function handle(): void {
        $overdue = WorkInstructionAcknowledgment::whereNull('acknowledged_at')
            ->where('deadline', '<', now())
            ->where('is_overdue', false)
            ->get();

        foreach ($overdue as $ack) {
            // Mark as overdue
            $ack->update(['is_overdue' => true]);

            // Send urgent reminder
            Notification::send($ack->employee,
                new WorkInstructionOverdueNotification($ack)
            );

            // Notify manager
            Notification::send($ack->employee->manager,
                new EmployeeHasOverdueAcknowledgment($ack)
            );
        }
    }
}
```

#### 4. Employee Acknowledgment Interface

```typescript
const WorkInstructionAcknowledgment: React.FC<Props> = ({ instruction }) => {
  const [hasScrolledToBottom, setHasScrolledToBottom] = useState(false);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string>>({});
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => {
      if (contentRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
        if (scrollTop + clientHeight >= scrollHeight - 50) {
          setHasScrolledToBottom(true);
        }
      }
    };

    contentRef.current?.addEventListener("scroll", handleScroll);
    return () => contentRef.current?.removeEventListener("scroll", handleScroll);
  }, []);

  const handleAcknowledge = async () => {
    await api.post(`/work-instructions/${instruction.id}/acknowledge`, {
      quiz_answers: quizAnswers,
    });

    // Redirect or show success
  };

  return (
    <div className="instruction-acknowledgment">
      <div className="instruction-header">
        <h1>{instruction.title}</h1>
        <p>
          Dienstanweisung Nr. {instruction.instruction_number} (Version {instruction.version})
        </p>
        <p>Gültig ab: {instruction.valid_from}</p>
        {instruction.deadline && (
          <Alert variant="warning">⚠️ Kenntnisnahme erforderlich bis: {instruction.deadline}</Alert>
        )}
      </div>

      <div
        ref={contentRef}
        className="instruction-content"
        dangerouslySetInnerHTML={{ __html: instruction.content_html }}
      />

      {instruction.quiz && (
        <div className="comprehension-quiz">
          <h3>Verständnisfragen</h3>
          {instruction.quiz.questions.map((q, idx) => (
            <QuizQuestion
              key={idx}
              question={q}
              onChange={(answer) => setQuizAnswers({ ...quizAnswers, [q.id]: answer })}
            />
          ))}
        </div>
      )}

      <div className="acknowledgment-actions">
        <label>
          <input type="checkbox" checked={hasScrolledToBottom} disabled={!hasScrolledToBottom} />
          Ich bestätige, dass ich diese Dienstanweisung vollständig gelesen und verstanden habe.
        </label>

        <button onClick={handleAcknowledge} disabled={!hasScrolledToBottom} className="btn-primary">
          Kenntnisnahme bestätigen
        </button>

        <p className="legal-notice">
          Ihre Bestätigung wird digital signiert und ist rechtlich bindend. Die Integrität wird via
          OpenTimestamp gesichert.
        </p>
      </div>
    </div>
  );
};
```

#### 5. Manager Dashboard: Acknowledgment Tracking

```
┌─────────────────────────────────────────────────────────────────┐
│ Dienstanweisungen - Kenntnisnahmen                             │
├─────────────────────────────────────────────────────────────────┤
│ DA-2025-003: Brandschutzmaßnahmen Objekt A                     │
│ Veröffentlicht: 20.10.2025  |  Deadline: 27.10.2025            │
│                                                                 │
│ ✅ Bestätigt: 12/15 Mitarbeiter (80%)                           │
│ ⏳ Ausstehend: 3 Mitarbeiter                                    │
│    - Max Mustermann (Deadline: heute)                          │
│    - Erika Musterfrau (Deadline: morgen)                       │
│    - John Doe (Deadline: 27.10.2025)                           │
│                                                                 │
│ [Erinnerung senden] [Details ansehen] [PDF exportieren]        │
└─────────────────────────────────────────────────────────────────┘
```

**Priority:** 🟠 P1 (High) - Compliance + operational efficiency

**Legal Risk:** 🟢 Low (improves compliance, reduces paper trail issues)

---

## 📅 Shift Planning (Dienstplanung)

### Requirement: Intelligent Shift Scheduling

**Context:**
Manual shift planning is time-consuming and error-prone:

- Ensuring coverage (enough staff per shift)
- Matching qualifications to requirements
- Respecting employee preferences (vacation, availability)
- Legal compliance (working time law, rest periods)
- Different planning horizons: Weekly, monthly, or annual

**Planning Frequencies:**

- **Weekly Planning:** Short-term flexibility, quick adjustments
- **Monthly Planning:** Most common, balance of predictability and flexibility
- **Annual Planning:** Long-term framework (especially for large contracts)

**SecPal Support:**

```php
Schema::create('shift_plan_periods', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('organization_id');
    $table->enum('period_type', ['weekly', 'monthly', 'quarterly', 'annual']);
    $table->date('period_start');
    $table->date('period_end');
    $table->enum('status', ['draft', 'published', 'locked']);
    $table->timestamps();
});
```

**Features:**

### 1. Shift Templates

**Define recurring shift patterns:**

```yaml
Shift Template: "Nachtschicht Objekt A"
  Time: 22:00 - 06:00
  Required Staff:
    - 2x Security Guard (§34a)
    - 1x First Aid Certified
  Location: "Objekt A, Berlin Mitte"
  Recurrence: Mo-Fr (weekly)
```

### 2. Qualification Requirements

**Per shift or location:**

```php
Schema::create('shift_requirements', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('shift_template_id')->nullable();
    $table->foreignUuid('location_id')->nullable();

    // Example: "Always 1 first aid certified guard on site"
    $table->foreignUuid('qualification_id');
    $table->integer('min_count')->default(1);

    $table->timestamps();
});
```

**Validation:**

- ⚠️ Warning when scheduling shift without required qualifications
- 🚨 Error when confirming shift with missing requirements

### 3. Auto-Scheduling Algorithm

**Input:**

- Shift templates (when/where/requirements)
- Employee availability (vacation, preferences, working time law)
- Employee qualifications
- Historical data (who worked together before)

**Algorithm (simplified):**

```php
class ShiftScheduler {
    public function autoSchedule(
        Carbon $startDate,
        Carbon $endDate,
        array $constraints
    ): Schedule {
        $shifts = $this->generateShifts($startDate, $endDate);

        foreach ($shifts as $shift) {
            $candidates = $this->findEligibleEmployees($shift);
            $selected = $this->optimizeSelection($candidates, $shift, $constraints);

            $shift->assignEmployees($selected);
        }

        return new Schedule($shifts);
    }

    private function findEligibleEmployees(Shift $shift): Collection {
        return Employee::where('status', 'active')
            ->whereDoesntHave('shifts', function ($q) use ($shift) {
                // No overlap with existing shifts
                $q->whereBetween('start_time', [$shift->start_time, $shift->end_time]);
            })
            ->whereHas('qualifications', function ($q) use ($shift) {
                // Has required qualifications
                $q->whereIn('qualification_id', $shift->requiredQualifications());
            })
            ->get();
    }

    private function optimizeSelection(
        Collection $candidates,
        Shift $shift,
        array $constraints
    ): Collection {
        // Scoring algorithm:
        // +10 points: Has worked this shift before
        // +5 points: Lives nearby (reduce travel time)
        // +3 points: No overtime this week (distribute evenly)
        // -5 points: Explicitly prefers not to work this time

        return $candidates->sortByDesc('score')->take($shift->required_count);
    }
}
```

**Constraints:**

- Working Time Law (ArbZG): Max 10h/day, 48h/week (avg over 6 months)
- Rest periods: Min 11h between shifts
- Employee preferences: Preferred shifts, blocked times
- Fair distribution: Avoid always scheduling same people for unpopular shifts

### 4. Employee Self-Service

**Mobile app features:**

- 📅 View own shifts (calendar view)
- 📝 Request vacation / time off
- 🔄 Request shift swaps (with colleague approval)
- ⭐ Mark shift preferences (prefer/avoid certain times)
- ✅ Confirm shift acceptance

**Workflow:**

```
Employee requests vacation (10.-15.11.2025)
  ↓
Manager receives notification
  ↓
Manager approves/rejects
  ↓
If approved: Auto-scheduler re-plans affected shifts
  ↓
Affected employees notified of changes
```

### 5. Understaffed Shift Alerts

**Alert Triggers:**

```php
// app/Console/Commands/CheckShiftCoverage.php
class CheckShiftCoverage extends Command {
    public function handle() {
        $futureShifts = Shift::where('start_time', '>', now())
                             ->where('start_time', '<', now()->addDays(14))
                             ->whereRaw('assigned_count < required_count')
                             ->get();

        foreach ($futureShifts as $shift) {
            $urgency = $shift->start_time->diffInDays(now()) < 3
                ? 'critical'
                : 'warning';

            Notification::send(
                $shift->location->managers,
                new UnderstaffedShiftNotification($shift, $urgency)
            );
        }
    }
}
```

**Dashboard Widget:**

```
┌─────────────────────────────────────────────────────┐
│ ⚠️ Unterbesetzte Schichten (nächste 14 Tage)       │
├─────────────────────────────────────────────────────┤
│ 🚨 Mo, 28.10. 22:00-06:00 Objekt A                 │
│    2/3 Mitarbeiter eingeteilt                       │
│    [Mitarbeiter hinzufügen]                         │
│                                                     │
│ ⚠️ Di, 29.10. 06:00-14:00 Objekt B                 │
│    4/5 Mitarbeiter eingeteilt                       │
│    [Mitarbeiter hinzufügen]                         │
└─────────────────────────────────────────────────────┘
```

**Priority:** 🟠 P1 (High) - High business value

---

### 6. Shift Plan Publication & Employee Notifications

**Context:**

Once shift plans are approved (including Works Council approval if required), employees need to be informed about their schedules. This can happen via:

1. **Email notifications** (automatic)
2. **Mobile app access** (employee self-service)
3. **Web portal access** (optional, personal devices)

**Workflow: Shift Plan Publication**

```
Manager creates shift plan (Draft)
  ↓
[If Works Council exists]
  Submit to BR for approval
  BR approves/rejects
  ↓
Manager publishes shift plan
  ↓
System triggers:
  ✅ Email notifications to all scheduled employees
  ✅ Mobile app push notifications
  ✅ Shift visible in employee calendar
  ↓
Employees can:
  - View shifts in mobile app
  - Receive automatic reminders (24h before shift)
  - Request changes (swap/vacation)
```

**Implementation: Email Notifications**

```php
// app/Events/ShiftPlanPublished.php
class ShiftPlanPublished {
    public function __construct(
        public ShiftPlan $plan
    ) {}
}

// app/Listeners/NotifyEmployeesOfNewShifts.php
class NotifyEmployeesOfNewShifts {
    public function handle(ShiftPlanPublished $event): void {
        $plan = $event->plan;

        // Get all employees scheduled in this plan
        $employees = $plan->shifts()
            ->with('assignedEmployees')
            ->get()
            ->pluck('assignedEmployees')
            ->flatten()
            ->unique('id');

        foreach ($employees as $employee) {
            // Send email notification
            Mail::to($employee->email)->send(
                new ShiftPlanAvailable($plan, $employee)
            );

            // Send push notification (if mobile app installed)
            if ($employee->hasPushToken()) {
                PushNotification::send($employee, [
                    'title' => 'Neuer Dienstplan verfügbar',
                    'body' => "Dein Dienstplan für {$plan->name} ist jetzt verfügbar.",
                    'action' => route('mobile.shifts.index')
                ]);
            }
        }
    }
}
```

**Configuration: Notification Settings**

```php
// Organization-level settings
Schema::table('organizations', function (Blueprint $table) {
    $table->jsonb('notification_settings')->nullable();
});

// Settings example
{
    "shift_plan_publication": {
        "email_notifications": true,
        "push_notifications": true,
        "advance_notice_days": 14,  // Publish plans min 14 days in advance
        "reminder_hours_before": 24 // Remind employees 24h before shift
    },
    "shift_changes": {
        "notify_on_change": true,
        "notify_on_swap": true
    }
}

// Employee-level preferences
Schema::table('employees', function (Blueprint $table) {
    $table->jsonb('notification_preferences')->nullable();
});

// Employee can opt out of certain notifications
{
    "email_shift_plans": true,
    "email_shift_changes": true,
    "email_shift_reminders": false, // Don't email reminders
    "push_shift_reminders": true    // But send push instead
}
```

**Email Template Example:**

```
Subject: Neuer Dienstplan verfügbar - November 2025

Hallo Max,

Dein Dienstplan für November 2025 ist jetzt verfügbar.

Deine Schichten:
- Mo, 04.11.2025, 22:00-06:00, Objekt A Berlin
- Mi, 06.11.2025, 22:00-06:00, Objekt A Berlin
- Fr, 08.11.2025, 22:00-06:00, Objekt A Berlin
... (12 weitere Schichten)

Gesamt: 15 Schichten, 120 Stunden

[Dienstplan ansehen] (Link zur App/Website)

Bei Fragen oder Änderungswünschen wende Dich an Deinen Dienstplan-Koordinator.

Viele Grüße,
SecPal Dienstplanung
```

**Automatic Shift Reminders:**

```php
// app/Console/Commands/SendShiftReminders.php
class SendShiftReminders extends Command {
    protected $signature = 'shifts:send-reminders';

    public function handle(): void {
        // Find shifts starting in 24 hours
        $upcomingShifts = Shift::whereBetween('start_time', [
            now()->addHours(23),
            now()->addHours(25)
        ])->with('assignedEmployees')->get();

        foreach ($upcomingShifts as $shift) {
            foreach ($shift->assignedEmployees as $employee) {
                // Check employee preferences
                if ($employee->wantsShiftReminders()) {
                    Notification::send($employee,
                        new ShiftReminderNotification($shift)
                    );
                }
            }
        }
    }
}

// Run every hour via cron
// * * * * * cd /path-to-your-project && php artisan schedule:run >> /dev/null 2>&1
```

### 7. Employee Access Control (Personal Devices)

**Requirement: Secure Access to Shift Schedules on Private Devices**

**Context:**

Employees want to check their schedules from personal phones/computers, but should **NOT have access to sensitive data** like:

- ❌ Guard book entries (client information, incidents)
- ❌ Other employees' personal data
- ❌ Client contracts or locations details

**SecPal Approach: Role-Based Access with Time Restrictions**

**Option A: Separate "Employee Portal" (Read-Only)**

```php
// Separate authentication domain: employees.secpal.app
Route::domain('employees.{organization}.secpal.app')->group(function () {
    Route::middleware(['auth:employee'])->group(function () {
        // LIMITED access
        Route::get('/shifts', [EmployeeShiftController::class, 'index']);
        Route::get('/qualifications', [EmployeeQualificationController::class, 'index']);
        Route::post('/vacation-requests', [VacationRequestController::class, 'store']);

        // BLOCKED routes (not accessible via employee portal)
        // Route::get('/guard-book', ...) // ❌ Not available
        // Route::get('/employees', ...) // ❌ Not available
    });
});
```

**Option B: Time-Based Access (Only During Work Hours)**

```php
// Middleware: app/Http/Middleware/EnforceWorkHoursAccess.php
class EnforceWorkHoursAccess {
    public function handle(Request $request, Closure $next): Response {
        $user = $request->user();

        // Check if user is currently on shift
        $activeShift = Shift::where('employee_id', $user->employee_id)
            ->where('start_time', '<=', now())
            ->where('end_time', '>=', now())
            ->first();

        // Guard book only accessible during active shift
        if ($request->is('guard-book/*') && !$activeShift) {
            abort(403, 'Wachbuch ist nur während Deiner Schicht verfügbar.');
        }

        return $next($request);
    }
}
```

**Option C: Device Whitelisting (Company Devices Only)**

```php
// Only allow guard book access from registered company devices
Schema::create('employee_devices', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('employee_id');
    $table->string('device_fingerprint')->unique(); // WebAuthn credential ID
    $table->enum('device_type', ['company_phone', 'company_tablet', 'personal']);
    $table->boolean('guard_book_access')->default(false); // Only true for company devices
    $table->timestamps();
});

// Middleware check
if ($request->is('guard-book/*')) {
    $device = $request->user()->devices()
        ->where('device_fingerprint', $request->deviceFingerprint())
        ->where('guard_book_access', true)
        ->first();

    if (!$device) {
        abort(403, 'Wachbuch-Zugriff nur von Firmengeräten erlaubt.');
    }
}
```

**Recommended Strategy:**

| Feature                    | Personal Device Access | Company Device Access |
| -------------------------- | ---------------------- | --------------------- |
| View own shift schedule    | ✅ Allowed             | ✅ Allowed            |
| Request vacation           | ✅ Allowed             | ✅ Allowed            |
| Request shift swaps        | ✅ Allowed             | ✅ Allowed            |
| View own qualifications    | ✅ Allowed             | ✅ Allowed            |
| Access guard book          | ❌ Blocked             | ✅ Only during shift  |
| View client information    | ❌ Blocked             | ✅ Only during shift  |
| View other employees       | ❌ Blocked             | ❌ Blocked            |
| Export data                | ❌ Blocked             | ❌ Blocked            |
| Checkpoint scanning (OWKS) | ❌ Blocked             | ✅ Allowed            |

**Database: Track Access Source**

```php
Schema::create('audit_log', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('user_id');
    $table->string('action'); // 'viewed_guard_book', 'downloaded_shift_plan'
    $table->string('resource_type'); // 'GuardBook', 'ShiftPlan'
    $table->uuid('resource_id')->nullable();
    $table->enum('device_type', ['company_device', 'personal_device']);
    $table->string('ip_address');
    $table->string('user_agent');
    $table->timestamp('accessed_at');
});
```

**Priority:** 🟠 P1 (High) - Employee satisfaction + security

---

## 👁️ Client Portal (Read-Only Access)

### Requirement: Client Transparency

**Context:**
Clients want to see what happens on their premises:

- Incident reports
- Patrol logs
- Guard attendance

**BUT:** Data protection (GDPR) forbids showing employee names to external parties.

**Solution: Pseudonymization**

**Client View:**

```json
{
  "shift": {
    "date": "2025-10-27",
    "time": "22:00 - 06:00",
    "location": "Objekt A",
    "guards": [
      {
        "guard_id": "G-1234", // Pseudonym
        "guard_alias": "Wache 1",
        "qualifications": ["§34a", "Erste Hilfe"] // No names!
      },
      {
        "guard_id": "G-5678",
        "guard_alias": "Wache 2",
        "qualifications": ["§34a", "Brandschutzhelfer"]
      }
    ]
  },
  "incidents": [
    {
      "time": "23:45",
      "type": "Routine Patrol",
      "description": "Rundgang ohne Befund",
      "reported_by": "Wache 1" // No real name
    }
  ]
}
```

**Client Portal Features:**

- ✅ View shifts for their locations only
- ✅ View incident reports (anonymized reporters)
- ✅ View patrol logs
- ✅ Export reports (PDF/CSV)
- ❌ No employee names
- ❌ No salary information
- ❌ No personal employee data
- ❌ No write access

**Access Control:**

```php
class ClientPolicy {
    public function viewShift(User $user, Shift $shift): bool {
        // Client can only see shifts at their own locations
        return $user->hasRole('client')
            && $user->client->locations->contains($shift->location_id);
    }

    public function viewEmployeeDetails(User $user): bool {
        // Clients never see employee details
        return $user->hasRole('client') ? false : true;
    }
}
```

**Priority:** 🟡 P2 (Medium) - Competitive feature, but not critical for MVP

---

## 📱 Mobile App for Employees

### Requirement: Employee Self-Service App

**Features:**

### 1. View Shift Schedule

- Calendar view (month/week/day)
- Shift details (location, time, colleagues)
- Color coding (confirmed/pending/past)

### 2. Time Off Requests

- Submit vacation requests
- Track approval status
- Remaining vacation days counter

### 3. Shift Swap Requests

```
Employee A wants to swap shift on 05.11.
  ↓
App shows eligible colleagues (not already scheduled)
  ↓
Employee B accepts swap
  ↓
Manager approves
  ↓
Shift reassigned
```

### 4. Guard Book Entry (Field Use)

- Quick incident reporting
- Photo upload (camera integration)
- GPS location capture
- Offline capability (sync when online)

### 5. Document Access

- View own employment contract (PDF)
- View own qualifications & expiry dates
- Download certificates

**Technology:**

- PWA (Progressive Web App) - Same as admin frontend
- Offline-first (ADR-003)
- Responsive design (mobile-first)

**Priority:** 🟡 P2 (Medium) - Improves employee satisfaction

---

## 🔍 OWKS Integration (Checkpoint Scanning)

### Requirement: Patrol Route Verification

**OWKS:** "Ordnungs- und Wachdienst-Kontrollsystem"

**Context:**
Guards must patrol routes and scan checkpoints to prove presence.

**Technologies:**

1. **NFC Tags** (**Primary - Recommended**)

   - NFC tags mounted at checkpoints (tamper-resistant housing)
   - Guard taps phone to scan
   - **Advantages:**
     - Works completely offline
     - Fast and reliable
     - Not forgeable (each tag has unique ID)
     - Weather-resistant mounting options
     - Long lifespan (10+ years passive tags)
   - **Cost:** ~€2-5 per tag (one-time investment)
   - **Use Case:** Professional installations where reliability matters

2. **QR Codes** (Cost-Effective Alternative)

   - Print QR codes, mount at checkpoints (laminated/weatherproof)
   - Guard scans with phone camera
   - **Advantages:**
     - Very cheap (~€0.50 per checkpoint with printing/lamination)
     - Easy to replace if damaged
     - No special hardware needed
   - **Disadvantages:**
     - ⚠️ Can be forged (photo/print of QR code)
     - Requires good lighting
     - Camera quality dependent
     - Lamination can degrade
   - **Use Case:** Budget-constrained deployments, indoor locations

3. **Bluetooth Beacons** (Under Consideration)
   - Beacons detect nearby phones (automatic check-in)
   - **Advantages:**
     - No manual scanning required
     - Can estimate proximity
   - **Disadvantages:**
     - Higher cost (~€20-40 per beacon + batteries)
     - Battery replacement needed (~1-2 years)
     - Connection reliability issues
     - Power consumption on mobile device
   - **Priority:** Future consideration (P4)

**Recommendation:** Start with NFC for professional clients, offer QR as budget option. Include security warning about QR code forgery in client education materials.

**Implementation:**

```php
Schema::create('checkpoints', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('location_id');
    $table->string('name'); // "Eingang Ost", "Parkdeck 2"
    $table->string('qr_code')->unique(); // Encrypted UUID
    $table->string('nfc_tag_id')->nullable();
    $table->jsonb('gps_coordinates')->nullable();
    $table->integer('scan_interval_minutes')->default(60); // Expected scan frequency
    $table->timestamps();
});

Schema::create('checkpoint_scans', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('checkpoint_id');
    $table->foreignUuid('employee_id');
    $table->foreignUuid('shift_id');
    $table->timestamp('scanned_at');
    $table->jsonb('gps_location_actual')->nullable(); // Where guard actually was
    $table->enum('scan_method', ['qr', 'nfc', 'bluetooth', 'manual']);
    $table->timestamps();
});
```

**Mobile App Flow:**

```
1. Guard starts shift → App activates checkpoint mode
2. Guard walks patrol route
3. Guard scans QR code at checkpoint
4. App records: Time, GPS, Checkpoint ID
5. If offline: Store locally, sync later
6. Dashboard shows patrol completion percentage
```

**Analytics:**

- Missed checkpoints (alert manager)
- Patrol route deviations
- Average patrol duration
- Checkpoint scan heatmap

**Priority:** 🟢 P3 (Low for MVP, but valuable feature)

---

## 📍 Device Management & Geofencing

### Requirement: Ensure Guards Use Company Devices

**Problem:**

- Guards should use company devices (not personal phones)
- Guards must be at location when clocking in/out
- GPS tracking raises data protection concerns

### 1. Device Recognition (Passkey-Based)

**Approach: WebAuthn / Passkeys**

```typescript
// Register company device
async function registerDevice(employeeId: string) {
  const credential = await navigator.credentials.create({
    publicKey: {
      challenge: new Uint8Array(32),
      rp: { name: "SecPal", id: "secpal.app" },
      user: {
        id: Uint8Array.from(employeeId, (c) => c.charCodeAt(0)),
        name: employee.email,
        displayName: employee.name,
      },
      pubKeyCredParams: [{ type: "public-key", alg: -7 }],
      authenticatorSelection: {
        authenticatorAttachment: "platform", // Device-bound
        requireResidentKey: true,
      },
    },
  });

  // Store credential ID in database
  await api.post("/devices/register", {
    employee_id: employeeId,
    credential_id: credential.id,
    device_name: "Samsung Galaxy A52", // From User-Agent
  });
}
```

**Benefits:**

- ✅ Device-bound authentication (can't use different device)
- ✅ No passwords (more secure)
- ✅ Biometric unlock (fingerprint/face)

**Database:**

```php
Schema::create('registered_devices', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('employee_id');
    $table->string('device_name');
    $table->text('credential_id'); // WebAuthn credential
    $table->text('public_key');
    $table->timestamp('registered_at');
    $table->timestamp('last_used_at')->nullable();
    $table->boolean('is_active')->default(true);
    $table->timestamps();
});
```

### 2. Geofencing (Location Verification)

**Requirement:** Verify guard is at location when clocking in/out

**Implementation:**

```php
Schema::create('locations', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->string('name'); // "Objekt A"
    $table->jsonb('gps_center'); // { lat: 52.520, lon: 13.405 }
    $table->integer('geofence_radius_meters')->default(100); // 100m tolerance
    $table->boolean('require_geofence_check')->default(true);
    $table->timestamps();
});

// Shift start with geofence check
class ClockInService {
    public function clockIn(
        Employee $employee,
        Shift $shift,
        float $lat,
        float $lon
    ): ShiftAttendance {
        $location = $shift->location;

        if ($location->require_geofence_check) {
            $distance = $this->calculateDistance(
                $lat, $lon,
                $location->gps_center['lat'],
                $location->gps_center['lon']
            );

            if ($distance > $location->geofence_radius_meters) {
                throw new GeofenceViolationException(
                    "Sie sind {$distance}m vom Objekt entfernt. Maximal {$location->geofence_radius_meters}m erlaubt."
                );
            }
        }

        return ShiftAttendance::create([
            'employee_id' => $employee->id,
            'shift_id' => $shift->id,
            'clocked_in_at' => now(),
            'clock_in_location' => compact('lat', 'lon'),
        ]);
    }
}
```

### 3. Data Protection Considerations

**⚠️ GPS Tracking is HIGHLY SENSITIVE under German labor law!**

**Legal Requirements:**

- ✅ Betriebsrat approval required (Works council)
- ✅ Employee consent required
- ✅ Only location at clock in/out (not continuous tracking)
- ✅ Purpose limitation (only for attendance verification)
- ✅ Data minimization (no historical location tracking)

**Best Practice:**

```yaml
GPS Usage Policy:
  - Location captured ONLY at:
      - Clock in (shift start)
      - Clock out (shift end)
      - Checkpoint scans (optional, configurable)
  - NOT captured:
      - During shift (continuous tracking)
      - During breaks
      - Outside working hours
  - Data retention:
      - 30 days (then deleted, unless legal dispute)
  - Employee rights:
      - View own location history
      - Dispute inaccurate geofence violations
```

**Consent Form:**

```
Einwilligung zur GPS-Ortung

Ich, [Name], erkläre mich einverstanden, dass SecPal meine GPS-Position
erfasst beim:
☑ Dienstbeginn (Clock-in)
☑ Dienstende (Clock-out)
☐ Kontrollpunkt-Scans (optional)

Ich wurde darüber informiert, dass:
- Die Ortung nur zu den oben genannten Zeitpunkten erfolgt
- Die Daten nach 30 Tagen gelöscht werden
- Ich diese Einwilligung jederzeit widerrufen kann

Datum: __________ Unterschrift: __________
```

**Priority:** 🟡 P2 (Medium) - Valuable but requires legal review

---

## 📊 Feature Prioritization Matrix

| Feature                    | Business Value | Complexity | Legal Risk | Priority | Target Version       |
| -------------------------- | -------------- | ---------- | ---------- | -------- | -------------------- |
| RBAC (Roles & Permissions) | 🔴 Critical    | Medium     | Low        | P0       | 0.2.0                |
| Employee Management        | 🔴 Critical    | Medium     | Medium     | P0       | 0.2.0                |
| Qualification Management   | 🟠 High        | Low        | Low        | P1       | 0.3.0                |
| Shift Planning (Manual)    | 🟠 High        | Medium     | Low        | P1       | 0.3.0                |
| Client Portal              | 🟡 Medium      | Low        | Medium     | P2       | 0.4.0                |
| Mobile App (Self-Service)  | 🟡 Medium      | High       | Low        | P2       | 0.5.0                |
| Auto-Scheduling            | 🟢 Nice        | Very High  | Low        | P3       | 1.1.0+               |
| OWKS / Checkpoints         | 🟢 Nice        | Medium     | Low        | P3       | 1.2.0+               |
| Device Management          | 🟢 Nice        | Medium     | Low        | P3       | 1.2.0+               |
| Geofencing                 | 🟢 Nice        | Low        | 🔴 High    | P3       | 2.0.0+ (After legal) |

---

## 🚀 Implementation Roadmap

### Version 0.2.0 - "Multi-User Foundation"

- [ ] RBAC system with predefined + custom roles
- [ ] Employee management (CRUD)
- [ ] Basic access control (who sees what)

### Version 0.3.0 - "Compliance & Planning"

- [ ] Qualification management
- [ ] Qualification expiry alerts
- [ ] Manual shift planning
- [ ] Shift templates

### Version 0.4.0 - "Client Features"

- [ ] Client portal (read-only)
- [ ] Pseudonymized guard book for clients
- [ ] Report exports (PDF/CSV)

### Version 0.5.0 - "Employee Empowerment"

- [ ] Mobile app (PWA)
- [ ] Shift calendar view
- [ ] Vacation requests
- [ ] Document access

### Version 1.0.0 - "Production Ready"

- [ ] All above features tested
- [ ] Legal review completed
- [ ] Performance optimization
- [ ] Security audit

### Version 1.1.0+ - "Advanced Features"

- [ ] Auto-scheduling algorithm
- [ ] Group training planner
- [ ] Advanced analytics

### Version 1.2.0+ - "Field Operations"

- [ ] OWKS checkpoint scanning
- [ ] Device management (Passkeys)
- [ ] Patrol route optimization

### Version 2.0.0+ - "Enterprise Features"

- [ ] Geofencing (after legal/Betriebsrat approval)
- [ ] Multi-organization support
- [ ] White-label capabilities

---

## 🔗 Related Documents

- `adr/`: Architecture decisions (technical implementation)
- `legal-compliance.md`: GDPR, BewachV, labor law requirements
- `ideas-backlog.md`: Long-term future features
- `planning.md`: How to convert these to GitHub Issues

---

## ✅ Next Steps

1. **Create ADR-004:** RBAC Architecture Decision
2. **Create GitHub Issues** for P0/P1 features (0.2.0, 0.3.0)
3. **Legal Review:** Geofencing, employee data handling, Betriebsrat
4. **Database Schema Design:** Employees, Qualifications, Shifts
5. **Prototype:** Manual shift planner UI

---

**Questions for Stakeholders:**

- [ ] Which qualification types are most common in your organization?
- [ ] How far in advance are shifts typically planned?
- [ ] Do you already use a Betriebsrat (works council)?
- [ ] Do clients currently request reports? How often?
- [ ] Are guards using personal or company devices today?
