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
- Future ADR: RBAC Architecture
- legal-compliance.md: GDPR access control requirements

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
Security guards require various qualifications:
- Mandatory: §34a Sachkundeprüfung (IHK certificate)
- Optional but valuable: First aid, fire safety, dog handling, weapons license
- Recurring: First aid (every 2 years), fire safety training

**Features:**

### 1. Qualification Types

**Predefined Qualifications:**
- §34a Sachkundeprüfung (mandatory)
- First Aid (Erste Hilfe)
- Fire Safety Officer (Brandschutzhelfer)
- Safety Officer (Sicherheitsbeauftragter)
- Dog Handler (Hundeführer)
- Weapons License (Waffenschein)
- NSL Certification (Geprüfte Schutz- und Sicherheitskraft)

**Custom Qualifications:**
- ✅ Add organization-specific qualifications
- ✅ Define if mandatory or optional
- ✅ Set renewal period (e.g., every 2 years)

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

## 📅 Shift Planning (Dienstplanung)

### Requirement: Intelligent Shift Scheduling

**Context:**
Manual shift planning is time-consuming and error-prone:
- Ensuring coverage (enough staff per shift)
- Matching qualifications to requirements
- Respecting employee preferences (vacation, availability)
- Legal compliance (working time law, rest periods)

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
        "guard_id": "G-1234",  // Pseudonym
        "guard_alias": "Wache 1",
        "qualifications": ["§34a", "Erste Hilfe"]  // No names!
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
      "reported_by": "Wache 1"  // No real name
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

1. **QR Codes** (cheapest)
   - Print QR codes, mount at checkpoints
   - Guard scans with phone camera
   - App records: Time, Location, Guard ID

2. **NFC Tags** (more robust)
   - NFC tags mounted at checkpoints
   - Guard taps phone
   - Works offline

3. **Bluetooth Beacons** (automatic)
   - Beacons detect nearby phones
   - Automatic check-in (no manual scan)
   - Higher cost

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
        id: Uint8Array.from(employeeId, c => c.charCodeAt(0)),
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
  await api.post('/devices/register', {
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

| Feature                    | Business Value | Complexity | Legal Risk | Priority | Target Version |
| -------------------------- | -------------- | ---------- | ---------- | -------- | -------------- |
| RBAC (Roles & Permissions) | 🔴 Critical    | Medium     | Low        | P0       | 0.2.0          |
| Employee Management        | 🔴 Critical    | Medium     | Medium     | P0       | 0.2.0          |
| Qualification Management   | 🟠 High        | Low        | Low        | P1       | 0.3.0          |
| Shift Planning (Manual)    | 🟠 High        | Medium     | Low        | P1       | 0.3.0          |
| Client Portal              | 🟡 Medium      | Low        | Medium     | P2       | 0.4.0          |
| Mobile App (Self-Service)  | 🟡 Medium      | High       | Low        | P2       | 0.5.0          |
| Auto-Scheduling            | 🟢 Nice        | Very High  | Low        | P3       | 1.1.0+         |
| OWKS / Checkpoints         | 🟢 Nice        | Medium     | Low        | P3       | 1.2.0+         |
| Device Management          | 🟢 Nice        | Medium     | Low        | P3       | 1.2.0+         |
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
