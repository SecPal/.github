<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-007: Flexible Organizational Structure & Multi-Level Hierarchies

**Status:** Proposed

**Date:** 2025-11-26

**Deciders:** @kevalyq

## Summary

This ADR defines the architecture for flexible, unlimited-depth organizational hierarchies in SecPal. **Two independent hierarchical systems** are implemented:

1. **Internal Structure** (`organizational_units`): Security service company hierarchy (Holding → Company → Region → Branch → Division)

   - For **internal employees** (Guards, Managers, Admins)
   - Access control via `user_internal_organizational_scopes`
   - Fine-grained RBAC: From branch-wide access down to specific object areas

2. **Customer Structure** (`customers`): External customer organizations (Corporate → Regional → Local)
   - For **customer users** (Client role)
   - Access control via `customer_user_accesses` + `customer_user_object_accesses`
   - Read-only access, completely independent from internal structure

**Key Technology:** Closure Table Pattern enables unlimited hierarchy depth, fast queries (O(1) for descendants), and seamless RBAC integration.

## Context

SecPal targets the German private security service industry, which encompasses organizations of vastly different sizes and structures:

- **Small operations:** 3-5 person businesses with direct customer relationships
- **Medium enterprises:** Regional companies with multiple branches (10-50 employees)
- **Large corporations:** National/international companies with complex hierarchies (hundreds to thousands of employees)

### Problem Statement

Security service companies have diverse organizational structures:

1. **Flat structures:** Small businesses where customers are managed directly without intermediate organizational layers
2. **Branch structures:** Regional branches managing local customers and objects
3. **Regional structures:** Multiple branches grouped into regions
4. **Holding structures:** Multiple subsidiaries (e.g., "ProSec Nord GmbH", "ProSec Süd GmbH") under a parent holding company
5. **Division structures:** Large companies with separate business units (e.g., "Aviation Security", "Event Security", "Industrial Security")

### Core Requirements

1. **Flexibility:** System must accommodate structures from 1 level (direct) to 10+ levels (holding → regional company → region → branch → division)
2. **No Artificial Limits:** Organizations must be able to define their own hierarchy depth
3. **Dynamic Growth:** Small companies should be able to start simple and add organizational layers as they grow
4. **Access Control Integration:** RBAC must respect organizational boundaries (e.g., "Regional Manager" sees all branches in their region)
5. **Customer Hierarchies:** Support for national customers with regional/local contact persons
6. **Object Segmentation:** Large objects (e.g., airports, industrial sites) need to be divided into areas with separate guard books

### Real-World Scenarios

#### Part A: Internal Organizational Structures (Security Service Company)

These scenarios show the **security service's own organizational structure** and how internal employees (Guards, Managers, Admins) access data based on their position in the hierarchy.

**Scenario 1: Small Security Service (Flat Structure)**

```
═══════════════════════════════════════════════════════════
INTERNAL: Sicherheitsdienst Schmidt (5 Mitarbeiter)
═══════════════════════════════════════════════════════════

organizational_units: [none - flat, all employees report directly]

Internal Employees & RBAC:
├─ User: Inhaber Schmidt
│  Role: Admin
│  Scope: All customers/objects (no restrictions)
│
├─ User: Einsatzleiter Müller
│  Role: Manager
│  Scope: All customers/objects
│
└─ Guards (3x)
   Role: Guard
   Scope: Own shifts only

Managed Customers (external):
├─ Kunde A (Bürogebäude) → Objekt 1 → Wachbuch
└─ Kunde B (Lagerhaus) → Objekt 2 → Wachbuch
```

**Scenario 2: Regional Security Service (Multi-Branch with Fine-Grained RBAC)**

```
═══════════════════════════════════════════════════════════
INTERNAL: SecureGuard GmbH (50 Mitarbeiter)
═══════════════════════════════════════════════════════════

organizational_units:
SecureGuard GmbH (company)
├─ Niederlassung Berlin (branch)
│  Internal Employees & Fine-Grained RBAC:
│  ├─ User: Niederlassungsleiter Berlin
│  │  Role: Manager
│  │  Scope: user_internal_organizational_scopes
│  │         → organizational_unit_id = Niederlassung Berlin
│  │         → access_level = 'full'
│  │         → Can see ALL customers/objects of Berlin branch
│  │
│  ├─ User: Objektleiter Objekt A (fine-grained!)
│  │  Role: Custom "Objektleiter"
│  │  Scope: user_object_scopes
│  │         → object_id = Objekt A (specific)
│  │         → Can manage ONLY Objekt A (all areas, all shifts)
│  │         → CANNOT see other objects
│  │
│  ├─ User: Schichtführer Nachtschicht (even more fine-grained!)
│  │  Role: Custom "Schichtführer"
│  │  Scope: user_object_scopes + object_area_scopes
│  │         → object_id = Objekt A
│  │         → object_area_id = "Haupteingang" (specific area)
│  │         → Can manage ONLY Haupteingang area at Objekt A
│  │         → CANNOT see other areas (e.g., Lager, Parkplatz)
│  │
│  └─ Guards (10x)
│     Role: Guard
│     Scope: Own shifts only
│
│  Managed Customers (external):
│  ├─ Kunde A → Objekt A (Einkaufszentrum, 3 areas)
│  └─ Kunde B → Objekt B (Büroturm, 1 area)
│
├─ Niederlassung Hamburg (branch)
│  Similar structure, manages Kunde C, Kunde D
│
└─ Niederlassung München (branch)
   Similar structure, manages Kunde E, Kunde F
```

**Scenario 3: Large Holding with Complex Hierarchy**

```
═══════════════════════════════════════════════════════════
INTERNAL: ProSec Holding (500+ Mitarbeiter, multi-level)
═══════════════════════════════════════════════════════════

organizational_units:
ProSec Holding (holding)
├─ ProSec Nord GmbH (company)
│  ├─ Region Berlin-Brandenburg (region)
│  │  ├─ Niederlassung Berlin (branch)
│  │  │  Fine-Grained RBAC Examples:
│  │  │  ├─ Niederlassungsleiter Berlin
│  │  │  │  → Sees all Berlin customers/objects
│  │  │  │
│  │  │  ├─ Objektleiter Flughafen Terminal 2
│  │  │  │  → Sees ONLY Flughafen (all areas)
│  │  │  │
│  │  │  ├─ Schichtführer Gates 1-10
│  │  │  │  → Sees ONLY area "Gates 1-10"
│  │  │  │  → NOT other areas (Gates 11-20, Check-In, etc.)
│  │  │  │
│  │  │  └─ Guards → Own shifts only
│  │  │
│  │  └─ Niederlassung Potsdam (branch)
│  │
│  ├─ Region Hamburg (region)
│  │  └─ Regionalleiter Hamburg
│  │     → Sees all branches under Region Hamburg
│  │
│  └─ Geschäftsführer ProSec Nord
│     → Sees ALL regions/branches under ProSec Nord
│
└─ ProSec Süd GmbH (company)
   └─ Region Bayern

Vorstand ProSec Holding (Admin)
→ Sees EVERYTHING across all subsidiaries
```

#### Part B: Customer Organizational Structures (External Organizations)

These scenarios show **customer hierarchies** and how external customer users (Client role) access data. This is **completely separate** from the security service's internal structure.

**Important:** Customer users have access to the **same RBAC system** as internal employees, but with **restricted permissions**:

- ✅ Same Role/Permission infrastructure (Spatie Laravel-Permission)
- ✅ Same hierarchical access patterns (corporate_wide → regional → specific objects)
- ✅ Same scope-based access control
- ❌ **But:** Typically **read-only** permissions only
- ❌ **No write access:** Cannot create/edit guard book entries, shifts, employees, etc.
- ❌ **Limited visibility:** Only see their own customer data, not internal org structure

**Typical Customer Permissions:**

```php
// Client Role - Read-only permissions
$clientRole = Role::findByName('Client', 'sanctum');
$clientRole->syncPermissions([
    'guard_book.read',          // Read guard book entries
    'reports.read',             // Read reports
    'reports.export',           // Export/download reports
    'shifts.read',              // See scheduled shifts
    'work_instructions.read',   // Read work instructions for their objects

    // NO write permissions:
    // 'guard_book.create' ❌
    // 'guard_book.update' ❌
    // 'shifts.create' ❌
    // 'employees.read' ❌ (security: don't expose guard names/data)
]);
```

**Advanced Customer Roles (Optional):**

Organizations may create **custom customer roles** with varying permission levels:

```php
// Example: VIP Customer with additional access
Role::create(['name' => 'VIP Client', 'guard_name' => 'sanctum'])
    ->syncPermissions([
        'guard_book.read',
        'reports.read',
        'reports.export',
        'shifts.read',
        'incidents.read',           // Additional: See incident details
        'analytics.read',           // Additional: Access to analytics dashboard
        // Still NO write access
    ]);

// Example: Limited Customer (minimal access)
Role::create(['name' => 'Limited Client', 'guard_name' => 'sanctum'])
    ->syncPermissions([
        'reports.read',             // Only read reports
        // No guard book access, no shift details
    ]);
```

**Scenario 4: Small Local Customer (Single Location)**

```
═══════════════════════════════════════════════════════════
CUSTOMER: Müller GmbH (small business, single location)
═══════════════════════════════════════════════════════════

customers:
  - Müller GmbH (type: 'local', parent: null)
    → Managed by: Niederlassung Berlin (internal assignment)

objects:
  - Bürogebäude Musterstraße 1
    → Guard Book: WB-2025-001

Customer Users (Client Role - READ-ONLY):
├─ User: Geschäftsführer Müller
│  Access: customer_user_accesses
│          → customer_id = Müller GmbH
│          → access_level = 'corporate_wide'
│          → Can READ guard book, reports
│          → NO write access, NO internal org structure visible
│
└─ User: Facility Manager
   Access: customer_user_object_accesses
           → object_id = Bürogebäude Musterstraße 1
           → allowed_actions = ["read_guard_book"]
           → Can READ ONLY this object's guard book

NOTE: Customer users do NOT see which internal branch manages them!
```

**Scenario 5: National Customer with Regional Structure**

```
═══════════════════════════════════════════════════════════
CUSTOMER: Rewe Group (large national customer)
═══════════════════════════════════════════════════════════

customers (with customer_closures for hierarchy):
Rewe Group (type: 'corporate', parent: null)

├─ Rewe Region Nord (type: 'regional', parent: Rewe Group)
│  ├─ Rewe Markt Hamburg Altona (type: 'local')
│  │  → Managed by: Niederlassung Hamburg (internal, invisible to customer)
│  │  → Object: Rewe Markt Hamburg Altona
│  │     → Guard Book: WB-REWE-HH-001
│  │
│  └─ Rewe Markt Berlin Prenzlauer Berg (type: 'local')
│     → Managed by: Niederlassung Berlin (internal, invisible)
│     → Object: Rewe Markt Berlin Prenzlauer Berg
│        → Guard Book: WB-REWE-BE-001
│
└─ Rewe Region Süd (type: 'regional', parent: Rewe Group)
   └─ Rewe Markt München Schwabing (type: 'local')
      → Managed by: Niederlassung München (internal, invisible)
      → Object: Rewe Markt München Schwabing
         → Guard Book: WB-REWE-MUC-001

Customer Users (Client Role - READ-ONLY):
├─ User: Rewe Konzern-Sicherheitsmanager
│  Access: customer_user_accesses
│          → customer_id = Rewe Group
│          → access_level = 'corporate_wide'
│          → Can READ all Rewe guard books nationwide
│          → Uses customer_closures to find all descendant objects
│          → NO write access
│
├─ User: Rewe Regional-Koordinator Nord
│  Access: customer_user_accesses
│          → customer_id = Rewe Region Nord
│          → access_level = 'regional'
│          → Can READ Rewe Nord objects (Hamburg, Berlin)
│          → CANNOT see Rewe Süd objects
│
└─ User: Marktleiter Hamburg Altona
   Access: customer_user_object_accesses
           → object_id = Rewe Markt Hamburg Altona
           → allowed_actions = ["read_guard_book", "read_reports"]
           → Can READ ONLY this store's guard book
           → CANNOT see other Rewe stores

CRITICAL: Rewe users do NOT see:
- SecureGuard's internal branch structure
- Which Niederlassung manages their stores
- Other customers' data
They only see their own customer hierarchy.
```

### Technical Challenges

1. **Arbitrary Depth:** How to model hierarchies without hardcoded levels (e.g., "branch" → "region" → "holding")?
2. **Efficient Queries:** How to quickly find "all objects under Regional Manager X's scope"?
3. **Flexible Types:** How to support custom organizational unit types beyond predefined ones?
4. **RBAC Integration:** How to grant permissions based on organizational hierarchy position?
5. **Multiple Wachbücher:** Should large objects support multiple guard books per area?

## Decision

We will implement a **Closure Table Pattern** for organizational hierarchies combined with flexible object area segmentation and event-based guard books.

### Key Architectural Principle: Separation of Internal & External Hierarchies

**Critical Design Decision:** SecPal maintains **two completely independent hierarchical systems**:

```
┌─────────────────────────────────────────────────────────────────┐
│ INTERNAL: Security Service Company Structure                    │
│ (organizational_units + organizational_unit_closures)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ProSec Holding                                                 │
│  └─ ProSec Nord GmbH                                            │
│     └─ Region Berlin-Brandenburg                                │
│        └─ Niederlassung Berlin                                  │
│           └─ [EMPLOYEES: Guards, Managers, Admins]              │
│              ├─ User: Regional Manager Berlin                   │
│              │  Role: Manager                                   │
│              │  Scope: user_internal_organizational_scopes      │
│              │         → Access to Niederlassung Berlin +       │
│              │           all customers/objects managed by it    │
│              │                                                  │
│              └─ User: Guard Max Mustermann                      │
│                 Role: Guard                                     │
│                 Scope: Own shifts only                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

                               ⬇  ⬇  ⬇
                         "manages/serves"
                    (customer_organizational_unit_assignments)
                               ⬇  ⬇  ⬇

┌─────────────────────────────────────────────────────────────────┐
│ EXTERNAL: Customer Organizations                                │
│ (customers + customer_closures)                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Rewe Group (customer, managed by Niederlassung Berlin)         │
│  └─ Rewe Region Nord                                            │
│     └─ Rewe Markt Hamburg Altona (object)                       │
│        └─ [CUSTOMER USERS: Client Role]                         │
│           ├─ User: Rewe Corporate Security Manager              │
│           │  Role: Client                                       │
│           │  Scope: customer_user_accesses                      │
│           │         → Access to ALL Rewe objects nationwide     │
│           │         → Read-only: guard books, reports           │
│           │         → NO write access                           │
│           │                                                     │
│           └─ User: Store Manager Hamburg                        │
│              Role: Client                                       │
│              Scope: customer_user_object_accesses               │
│                     → Access ONLY to this specific store        │
│                     → Read-only: guard book for this object     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

KEY DIFFERENCES:
- Internal employees (Guards, Managers): Full CRUD access within their scope
- Customer users (Clients): Typically read-only access to their objects
- Internal org structure is INVISIBLE to customer users
- Customer hierarchy is VISIBLE to internal employees (for management)

SHARED RBAC INFRASTRUCTURE:
- Both use same Role/Permission system (Spatie Laravel-Permission)
- Both use same Guard ('sanctum')
- Both use hierarchical scope patterns
- Difference is in ASSIGNED permissions, not technical infrastructure
- Customer roles have restricted permission sets (usually read-only)
```

### Architecture Components

#### 1. Internal Organizational Units (Security Service Company Structure)

**Purpose:** Represents the **security service company's** internal structure (holding, branches, divisions, etc.). This is for **internal employees only** (guards, managers, admins).

**Core Table:**

```php
Schema::create('organizational_units', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');

    // Flexible type system for INTERNAL organization
    $table->enum('type', [
        'holding',           // Konzern/Holding (e.g., "ProSec Holding")
        'company',           // Gesellschaft (e.g., "ProSec Nord GmbH")
        'region',            // Region (e.g., "Region Berlin-Brandenburg")
        'branch',            // Niederlassung (e.g., "Niederlassung Berlin")
        'division',          // Sparte/Abteilung (e.g., "Event Security")
        'department',        // Bereich (e.g., "Operations Team Nord")
        'custom'             // User-defined type
    ]);

    $table->string('name'); // "ProSec Nord GmbH", "Region Berlin-Brandenburg"
    $table->string('custom_type_name')->nullable(); // If type='custom': "Einsatzgebiet"
    $table->text('description')->nullable();

    // Optional metadata (addresses, contact info, etc.)
    $table->jsonb('metadata')->nullable();

    $table->timestamps();
    $table->softDeletes();

    $table->comment('Internal organizational structure of the security service company');
});
```

**Closure Table (Hierarchy Storage):**

```php
Schema::create('organizational_unit_closures', function (Blueprint $table) {
    $table->foreignUuid('ancestor_id')
        ->references('id')->on('organizational_units')
        ->cascadeOnDelete();
    $table->foreignUuid('descendant_id')
        ->references('id')->on('organizational_units')
        ->cascadeOnDelete();
    $table->integer('depth'); // 0=self, 1=direct child, 2=grandchild, etc.

    $table->primary(['ancestor_id', 'descendant_id']);
    $table->index('depth');
    $table->index(['ancestor_id', 'depth']); // Fast ancestor queries
    $table->index(['descendant_id', 'depth']); // Fast descendant queries
});
```

**Key Properties:**

- **Unlimited Depth:** `depth` is an integer (0 to practically unlimited)
- **Fast Queries:** "All descendants of unit X" = simple `WHERE ancestor_id = X`
- **Self-Reference:** Every unit has entry with `depth=0` (ancestor=descendant=self)
- **Path Independence:** No need to store/traverse paths, all relationships pre-computed

#### 2. Customers (External Organizations - Separate from Internal Structure)

**Purpose:** Represents **external customer organizations**. This is completely independent from the security service's internal organizational structure.

```php
Schema::create('customers', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');

    $table->string('customer_number')->unique();
    $table->string('name'); // "Rewe Group", "Deutsche Bahn AG"
    $table->text('address')->nullable();

    // Optional: Customer hierarchy (for large external customers)
    // Example: Rewe Group → Rewe Region Nord → Rewe Markt Hamburg
    $table->foreignUuid('parent_customer_id')->nullable()
        ->references('id')->on('customers')
        ->nullOnDelete();

    $table->enum('type', [
        'corporate',        // National/international customer (e.g., "Rewe Group")
        'regional',         // Regional division (e.g., "Rewe Region Nord")
        'local',            // Single location (e.g., "Rewe Markt Hamburg Altona")
        'contact_person'    // On-site contact (not a real customer)
    ])->default('local');

    $table->timestamps();
    $table->softDeletes();

    $table->comment('External customer organizations - independent from internal org structure');
});

// Optional: Customer Closure Table (if customer hierarchies become complex)
// For simple parent-child relationships, parent_customer_id is sufficient
// For complex hierarchies (e.g., national chains), use closure table pattern:
Schema::create('customer_closures', function (Blueprint $table) {
    $table->foreignUuid('ancestor_id')
        ->references('id')->on('customers')
        ->cascadeOnDelete();
    $table->foreignUuid('descendant_id')
        ->references('id')->on('customers')
        ->cascadeOnDelete();
    $table->integer('depth'); // 0=self, 1=direct child, etc.

    $table->primary(['ancestor_id', 'descendant_id']);
    $table->index('depth');

    $table->comment('Optional: Closure table for complex customer hierarchies');
});

// Link customers to internal organizational units (which branch/region manages this customer?)
Schema::create('customer_organizational_unit_assignments', function (Blueprint $table) {
    $table->foreignUuid('customer_id')->references('id')->on('customers')->cascadeOnDelete();
    $table->foreignUuid('organizational_unit_id')
        ->references('id')->on('organizational_units')->cascadeOnDelete();

    // Which internal org unit is responsible for this customer?
    $table->enum('responsibility_type', [
        'primary',          // Main responsible unit (e.g., Niederlassung Berlin)
        'secondary',        // Secondary support
        'billing',          // Billing/invoicing responsibility
    ])->default('primary');

    $table->timestamps();

    $table->comment('Links external customers to internal organizational units (who manages this customer?)');
});

```

````

#### 3. Objects (Locations)

```php
Schema::create('objects', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');
    $table->foreignUuid('customer_id')->constrained('customers');

    $table->string('object_number')->unique();
    $table->string('name'); // "Einkaufszentrum Alexanderplatz"
    $table->text('address');
    $table->jsonb('gps_coordinates')->nullable(); // { "lat": 52.520, "lon": 13.405 }

    $table->timestamps();
    $table->softDeletes();
});
````

#### 4. Object Areas (Optional Segmentation)

```php
Schema::create('object_areas', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');
    $table->foreignUuid('object_id')->constrained('objects')->cascadeOnDelete();

    $table->string('name'); // "Haupteingang", "Lager Halle 3", "Parkplatz"
    $table->text('description')->nullable();

    // Optional: Geofencing boundaries (for location verification)
    $table->jsonb('gps_boundaries')->nullable(); // Polygon coordinates

    // Does this area require a separate guard book?
    $table->boolean('requires_separate_guard_book')->default(false);

    $table->timestamps();
    $table->softDeletes();
});
```

#### 5. Guard Books (Event Stream Containers)

**Core Concept:** Guard books are **not closed physical books** but continuous event streams. Reports can be generated from events for any time period.

```php
Schema::create('guard_books', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');

    // EITHER entire object OR specific area (mutually exclusive)
    $table->foreignUuid('object_id')->nullable()
        ->references('id')->on('objects')->cascadeOnDelete();
    $table->foreignUuid('object_area_id')->nullable()
        ->references('id')->on('object_areas')->cascadeOnDelete();

    // At least one must be set (PostgreSQL CHECK constraint)
    // CHECK (object_id IS NOT NULL OR object_area_id IS NOT NULL)
    // CHECK (NOT (object_id IS NOT NULL AND object_area_id IS NOT NULL))

    $table->string('name'); // "Wachbuch Haupteingang", "Wachbuch Gesamtobjekt"
    $table->enum('scope_type', [
        'object_wide',      // Entire object (default)
        'area_specific',    // Specific area only
        'custom'            // User-defined
    ])->default('object_wide');

    // Guard books are continuous, not "closed"
    $table->boolean('is_active')->default(true);
    $table->timestamp('archived_at')->nullable(); // When deactivated

    $table->timestamps();
    $table->softDeletes();
});
```

#### 6. Guard Book Reports (Generated from Events)

**Concept:** Reports are **compiled views** of events, not the events themselves. Users can generate reports for any time period with custom filters.

```php
Schema::create('guard_book_reports', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys');
    $table->foreignUuid('guard_book_id')->constrained('guard_books');

    $table->string('report_number')->unique(); // "BER-2025-001"
    $table->string('title'); // "Wochenbericht KW 47", "Monatsbericht November 2025"

    // Time period covered by this report (flexible!)
    $table->timestamp('period_start');
    $table->timestamp('period_end');

    // Filter criteria applied when generating report
    $table->jsonb('filter_criteria')->nullable();
    // Example: {"event_types": ["incident", "patrol"], "severity": "high", "exclude_routine": true}

    // Generated content
    $table->text('content_html')->nullable();
    $table->string('pdf_path')->nullable();
    $table->binary('ots_proof')->nullable(); // OpenTimestamp proof

    // Metadata
    $table->foreignUuid('generated_by_user_id')->references('id')->on('users');
    $table->timestamp('generated_at');
    $table->enum('status', ['draft', 'finalized', 'submitted_to_customer', 'archived']);

    $table->timestamps();
    $table->softDeletes();
});
```

#### 7. RBAC Integration (Internal Employee Scopes)

**Purpose:** Define access scopes for **internal employees** based on the security service's organizational structure.

````php
Schema::create('user_internal_organizational_scopes', function (Blueprint $table) {
    $table->foreignUuid('user_id')->references('id')->on('users')->cascadeOnDelete();
    $table->foreignUuid('organizational_unit_id')
        ->references('id')->on('organizational_units')->cascadeOnDelete();

    $table->enum('access_level', [
        'full',              // Full access to this unit + ALL descendants
        'read_only',         // Read-only access to this unit + descendants
        'specific_objects'   // Only specific objects (see user_object_scopes)
    ]);

    $table->primary(['user_id', 'organizational_unit_id'], 'user_internal_org_scopes_pk');
    $table->timestamps();

    $table->comment('Internal employee access scopes based on organizational hierarchy');
});

Schema::create('user_object_scopes', function (Blueprint $table) {
    $table->foreignUuid('user_id')->references('id')->on('users')->cascadeOnDelete();
    $table->foreignUuid('object_id')->references('id')->on('objects')->cascadeOnDelete();

    $table->enum('access_level', ['full', 'read_only']);

    $table->primary(['user_id', 'object_id']);
    $table->timestamps();

    $table->comment('Fine-grained: User access to specific objects (e.g., Objektleiter)');
});

// Even more fine-grained: Access to specific areas within objects
Schema::create('user_object_area_scopes', function (Blueprint $table) {
    $table->foreignUuid('user_id')->references('id')->on('users')->cascadeOnDelete();
    $table->foreignUuid('object_area_id')->references('id')->on('object_areas')->cascadeOnDelete();

    $table->enum('access_level', ['full', 'read_only']);

    $table->primary(['user_id', 'object_area_id'], 'user_object_area_scopes_pk');
    $table->timestamps();

    $table->comment('Ultra-fine-grained: User access to specific areas (e.g., Schichtführer Haupteingang)');
});
```**Access Control Query Example (Internal Employees):**

```php
// Find all objects accessible to internal user X based on organizational scope
$accessibleObjects = Object::query()
    ->whereHas('customerAssignments.organizationalUnit.descendants', function($q) use ($userId) {
        $q->whereIn('organizational_units.id', function($subQ) use ($userId) {
            $subQ->select('ancestor_id')
                ->from('organizational_unit_closures')
                ->whereIn('descendant_id', function($scopeQ) use ($userId) {
                    $scopeQ->select('organizational_unit_id')
                        ->from('user_internal_organizational_scopes')
                        ->where('user_id', $userId)
                        ->where('access_level', '!=', 'specific_objects');
                });
        });
    })
    ->orWhereHas('objectScopes', function($q) use ($userId) {
        $q->where('user_id', $userId);
    })
    ->get();

// Example: Regional Manager Berlin sees all objects managed by Niederlassung Berlin + sub-units
````

**Access Control Query Example (Customer Users):**

```php
// Find all objects accessible to customer user X
$accessibleObjects = Object::query()
    ->where('customer_id', function($q) use ($userId) {
        // Get customer(s) this user has access to
        $q->select('customer_id')
            ->from('customer_user_accesses')
            ->where('user_id', $userId);
    })
    ->when($corporateWideAccess, function($query) use ($customerId) {
        // If corporate-wide: Include all descendant customers
        $query->orWhereIn('customer_id', function($subQ) use ($customerId) {
            $subQ->select('descendant_id')
                ->from('customer_closures')
                ->where('ancestor_id', $customerId);
        });
    })
    ->orWhereHas('customerObjectAccesses', function($q) use ($userId) {
        // Or specific object access
        $q->where('user_id', $userId);
    })
    ->get();

// Example: Rewe Corporate Security Manager sees ALL Rewe objects nationwide
// Example: Rewe Store Manager Hamburg sees ONLY their specific store

// IMPORTANT: Apply permission checks after scope filtering
// Customer users may have scope but still need proper permissions (e.g., 'guard_book.read')
$guardBook = GuardBook::where('object_id', $objectId)->firstOrFail();

// Check both scope AND permission
if (!$user->hasPermissionTo('guard_book.read')) {
    abort(403, 'Missing permission: guard_book.read');
}
// Scope check already done via query above
```

#### 8. Customer User Access (External Client Access - Separate System)

**Purpose:** Define access rights for **external customer users** (Client Role). This is completely separate from internal employee RBAC.

**Key Difference:**

- **Internal RBAC:** Guards, Managers, Admins → Access based on organizational_units
- **Customer Access:** Client users → Access based on customer hierarchy + specific objects

```php
Schema::create('customer_user_accesses', function (Blueprint $table) {
    $table->foreignUuid('user_id')->references('id')->on('users')->cascadeOnDelete();
    $table->foreignUuid('customer_id')->references('id')->on('customers')->cascadeOnDelete();

    $table->enum('access_level', [
        'corporate_wide',    // Access to all sub-customers and objects (e.g., Rewe Corporate Security Manager)
        'regional',          // Only specific region (e.g., Rewe Regional Coordinator Nord)
        'specific_objects'   // Only specific objects (e.g., Store Manager)
    ]);

    $table->primary(['user_id', 'customer_id']);
    $table->timestamps();

    $table->comment('External customer user access rights - independent from internal RBAC');
});

Schema::create('customer_user_object_accesses', function (Blueprint $table) {
    $table->foreignUuid('user_id')->references('id')->on('users')->cascadeOnDelete();
    $table->foreignUuid('object_id')->references('id')->on('objects')->cascadeOnDelete();

    // What can this customer user see/do? (Limited compared to internal users)
    $table->jsonb('allowed_actions')->default('["read_guard_book"]');
    // Examples: ["read_guard_book", "read_reports", "view_incidents"]
    // NOTE: Customers should NEVER have write access (create/update/delete)

    $table->primary(['user_id', 'object_id']);
    $table->timestamps();

    $table->comment('Object-specific access for customer users - read-only, limited scope');
});
```

### Why Closure Table Pattern?

**Alternatives Considered:**

1. **Adjacency List (parent_id):** Simple but requires recursive queries for hierarchies
2. **Nested Set:** Fast reads but complex updates (requires recalculating all nodes)
3. **Materialized Path:** Stores full path as string (e.g., "/1/5/23/") - less flexible
4. **Closure Table:** Pre-computes all ancestor-descendant relationships

**Decision Rationale:**

| Criterion                  | Adjacency List      | Nested Set   | Materialized Path | Closure Table       |
| -------------------------- | ------------------- | ------------ | ----------------- | ------------------- |
| Read Performance (subtree) | ❌ Poor (recursive) | ✅ Excellent | ✅ Good           | ✅ Excellent        |
| Write Performance (insert) | ✅ Excellent        | ❌ Poor      | ⚠️ Fair           | ⚠️ Fair             |
| Write Performance (move)   | ✅ Excellent        | ❌ Poor      | ❌ Poor           | ⚠️ Fair             |
| Arbitrary Depth            | ✅ Yes              | ✅ Yes       | ✅ Yes            | ✅ Yes              |
| Query Simplicity           | ❌ Complex          | ✅ Simple    | ✅ Simple         | ✅ Simple           |
| Storage Overhead           | ✅ Minimal          | ✅ Minimal   | ✅ Minimal        | ⚠️ O(n²) worst case |

**Why Closure Table wins for SecPal:**

1. ✅ **Read-Heavy Workload:** Both organizational structures (internal + customer) are read frequently (permission checks, customer reports), modified rarely
2. ✅ **Simple Queries:** "All descendants" = `SELECT * WHERE ancestor_id = X` (works for both hierarchies)
3. ✅ **Unlimited Depth:** No artificial limits for either internal org structure or customer hierarchies
4. ✅ **Easy RBAC Integration:**
   - Internal: "User has scope on unit X" → automatically includes all descendants
   - Customer: "Customer user has corporate_wide access" → automatically includes all sub-customers
5. ⚠️ **Storage Overhead Acceptable:** Even 1000 org units + 1000 customers = ~1M closure records (negligible with modern databases)
6. ✅ **Separation of Concerns:** Each hierarchy (internal, customer) has its own closure table, no interference

## Consequences

### Positive

✅ **Maximum Flexibility:**

- Organizations can start simple (1-level) and grow to complex hierarchies (10+ levels)
- No hardcoded limits on depth
- Custom organizational unit types supported

✅ **Clear Separation of Concerns:**

- **Internal structure** (security service) completely separate from **customer structure**
- No confusion between employee RBAC and customer access rights
- Each system can evolve independently

✅ **Scalability:**

- Closure table performs well even with deep hierarchies
- Indexes on `ancestor_id`, `descendant_id`, `depth` ensure fast queries
- Read performance O(1) for "all descendants" queries

✅ **RBAC Integration:**

- Natural fit: "User has access to org unit X" = access to all descendants
- Policies can efficiently check organizational scope
- Supports hierarchical managers (Regional Manager → all branches)

✅ **Customer Hierarchies:**

- National customers with regional/local contacts
- Corporate-wide access vs. location-specific access
- Flexible permission levels (corporate_wide, regional, specific_objects)

✅ **Object Segmentation:**

- Large objects can be divided into areas
- Each area can have separate guard book (optional)
- Supports complex facilities (airports, industrial sites, shopping centers)

✅ **Guard Book Evolution:**

- Guard books as continuous event streams (not closed books)
- Reports generated on-demand for any time period
- Flexible filtering (weekly, monthly, annual, custom)
- Supports multiple report types (internal, customer, compliance)

### Negative

❌ **Complexity:**

- Closure table requires understanding of graph relationships
- Insert/update operations need to maintain closure records
- Developers must be familiar with pattern to avoid mistakes

❌ **Storage Overhead:**

- Closure table grows quadratically with hierarchy depth (O(n²) worst case)
- Example: 100 units with depth 5 = ~2500 closure records
- Mitigation: Acceptable for organizational hierarchies (typically <1000 units)

❌ **Write Performance:**

- Moving a subtree requires updating many closure records
- Mitigation: Organizational structures change rarely (acceptable overhead)

❌ **Learning Curve:**

- Team must understand closure table pattern
- Queries look different from traditional `parent_id` approaches
- Mitigation: Provide Eloquent models with helper methods

### Mitigations

**Eloquent Model Helpers:**

```php
class OrganizationalUnit extends Model
{
    // Get all descendants (children, grandchildren, etc.)
    public function descendants()
    {
        return $this->belongsToMany(
            OrganizationalUnit::class,
            'organizational_unit_closures',
            'ancestor_id',
            'descendant_id'
        )->where('depth', '>', 0);
    }

    // Get all ancestors (parent, grandparent, etc.)
    public function ancestors()
    {
        return $this->belongsToMany(
            OrganizationalUnit::class,
            'organizational_unit_closures',
            'descendant_id',
            'ancestor_id'
        )->where('depth', '>', 0);
    }

    // Get direct children only
    public function children()
    {
        return $this->descendants()->wherePivot('depth', 1);
    }

    // Get direct parent only
    public function parent()
    {
        return $this->ancestors()->wherePivot('depth', 1)->first();
    }
}
```

**Transaction-Safe Updates:**

```php
// Moving a unit to a new parent
DB::transaction(function () use ($unit, $newParent) {
    // 1. Remove old ancestor relationships (except self)
    DB::table('organizational_unit_closures')
        ->where('descendant_id', $unit->id)
        ->where('depth', '>', 0)
        ->delete();

    // 2. Add new ancestor relationships
    $ancestors = $newParent->ancestors()->pluck('id');
    $ancestors->push($newParent->id);

    foreach ($ancestors as $index => $ancestorId) {
        DB::table('organizational_unit_closures')->insert([
            'ancestor_id' => $ancestorId,
            'descendant_id' => $unit->id,
            'depth' => $index + 1
        ]);
    }
});
```

## Implementation Plan

### Phase 1: Foundation (Organizational Units)

- [ ] Create migrations for `organizational_units` and `organizational_unit_closures`
- [ ] Implement `OrganizationalUnit` model with closure table relationships
- [ ] Add helper methods (`descendants()`, `ancestors()`, `children()`, `parent()`)
- [ ] Write tests for hierarchy operations (insert, move, delete)
- [ ] Add API endpoints for CRUD operations

### Phase 2: Customers & Objects

- [ ] Create migrations for `customers`, `objects`, `object_areas`
- [ ] Implement models with relationships to organizational units
- [ ] Add customer hierarchy support (optional `parent_customer_id`)
- [ ] Write tests for customer-object relationships
- [ ] Add API endpoints

### Phase 3: Guard Books & Reports

- [ ] Create migrations for `guard_books` and `guard_book_reports`
- [ ] Implement guard book as event stream container (not closed book)
- [ ] Add object area segmentation support
- [ ] Implement report generation service (filter events by criteria)
- [ ] Write tests for multi-area objects
- [ ] Add API endpoints

### Phase 4: RBAC Integration

- [ ] Create migrations for `user_organizational_scopes` and `user_object_scopes`
- [ ] Implement policies that check organizational hierarchy
- [ ] Add customer user access tables (`customer_user_accesses`, `customer_user_object_accesses`)
- [ ] Write tests for hierarchical permission checks
- [ ] Add API endpoints for scope management

### Phase 5: Documentation & UI

- [ ] Update feature requirements with detailed use cases
- [ ] Create user documentation for organizational structure management
- [ ] Implement UI for org unit hierarchy visualization
- [ ] Add UI for object area management
- [ ] Create guide for hierarchical access control setup

## References

- **Related ADRs:**

  - [ADR-001: Event Sourcing for Guard Book Entries](20251027-event-sourcing-for-guard-book.md)
  - [ADR-004: RBAC System with Spatie Laravel-Permission](20251108-rbac-spatie-temporal-extension.md)
  - [ADR-005: RBAC Design Decisions](20251111-rbac-design-decisions.md)

- **Related Issues:**

  - Issue #5: RBAC System (Scope-based permissions)
  - Future Epic: Flexible Organizational Structure (TBD)

- **External Resources:**
  - [Closure Table Pattern](https://www.slideshare.net/billkarwin/models-for-hierarchical-data)
  - [PostgreSQL Recursive Queries](https://www.postgresql.org/docs/current/queries-with.html)
  - [Laravel Eloquent: Many-to-Many Relationships](https://laravel.com/docs/eloquent-relationships#many-to-many)

## Notes

- **Tenant Isolation:** All tables include `tenant_id` for multi-tenancy support
- **Soft Deletes:** All main tables use soft deletes to preserve referential integrity
- **UUIDs:** All primary keys are UUIDs for distributed systems and avoiding enumeration attacks
- **JSON Flexibility:** `metadata` and `filter_criteria` fields provide extensibility without schema changes
- **PostgreSQL Features:** Leverage `jsonb` for efficient JSON queries, `CHECK` constraints for data integrity

### Critical Separation Principle

**Two Independent Systems:**

1. **Internal Organizational Structure** (`organizational_units`)

   - Security service company hierarchy (Holding → Region → Branch)
   - For **internal employees only** (Guards, Managers, Admins)
   - Access control via `user_internal_organizational_scopes`
   - Full CRUD permissions within scope

2. **Customer Organization Structure** (`customers`)
   - External customer hierarchy (Corporate → Regional → Local)
   - For **customer users only** (Client role)
   - Access control via `customer_user_accesses` + `customer_user_object_accesses`
   - Read-only access, limited scope

**Key Insight:** A customer (e.g., "Rewe Group") is **managed by** an internal organizational unit (e.g., "Niederlassung Berlin"), but the two hierarchies remain completely separate. Internal employees see both hierarchies (for management), customer users see only their own structure (for access control).

**RBAC Infrastructure:** Both internal employees AND customer users share the **same technical RBAC system** (Spatie Laravel-Permission, Sanctum guard, hierarchical scopes). The difference is in **assigned permissions**: internal roles have CRUD capabilities (`guard_book.create`, `object.update`), while customer roles typically have read-only access (`guard_book.read`, `reports.export`).
