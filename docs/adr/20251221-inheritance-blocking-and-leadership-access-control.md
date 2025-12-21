<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-009: Permission Inheritance Blocking & Leadership-Based Access Control

## Status

**Proposed** (Draft - awaiting review)

## Date

2025-12-21

## Context

### The Problem: GDPR Compliance & Hierarchical Access Control

SecPal's organizational hierarchy system (ADR-007) enables complex multi-level structures representing holding companies, subsidiaries, branches, and divisions. Two critical challenges arise:

1. **GDPR Compliance:** Legally independent subsidiaries within hierarchies require data isolation
2. **Hierarchical Access Control:** Leadership roles need granular access based on organizational position

#### Challenge 1: Data Isolation for Legal Entities

**Real-World Scenario:**

```
Holding AG (Root Organization)
├── HR Department (internal)
├── IT Department (internal)
├── Branch Munich (internal)
└── Regional GmbH (legally independent subsidiary)
    └── HR Department Regional
```

**GDPR Requirements (Article 5(1)(c) - Data Minimization):**

- ✅ Holding HR can access Holding AG employee records
- ✅ Holding HR can access internal departments
- ❌ Holding HR **cannot** access Regional GmbH employee records (separate legal entity)
- ✅ Regional GmbH must have autonomous HR management

**Current Limitation:** All-or-nothing inheritance (`include_descendants = true/false`)

#### Challenge 2: Leadership-Based Access Restrictions

**Real-World Scenario:**

```
Niederlassung Berlin
├── Branch Director (Leadership Level 3)
├── Area Manager Operations (Leadership Level 5)
├── Area Manager Security (Leadership Level 5)
├── Site Manager (Leadership Level 6)
└── Guards (no leadership level)
```

**Business Requirements:**

- ✅ Branch Director sees all employees in branch
- ✅ Area Manager Operations sees **only** their operational team (not Security team)
- ✅ Area Manager Operations sees subordinates but **not** peer Area Managers
- ✅ Area Manager Operations **cannot** see Branch Director's HR data
- ✅ Guards see no HR data

**Current Limitation:** No horizontal access control (peers can see each other's HR data)

### GDPR Legal Requirements

**Article 5(1)(c) - Data Minimization:**

> Personal data shall be adequate, relevant and limited to what is necessary.

**Article 32 - Security of Processing:**

> Technical and organizational measures to ensure appropriate security.

**Application to SecPal:**

- Need-to-Know principle: Users only access data necessary for their role
- Hierarchical boundaries: Leadership can view subordinates, not peers or superiors
- Legal entity boundaries: Subsidiaries control their own data

---

## Decision

We implement **two complementary security mechanisms**:

### 1. Permission Inheritance Blocking (Organizational Autonomy)

**Concept:** Organizational units can **block specific permissions** from being inherited from ancestor units, even when `include_descendants = true` is set.

**Use Case:** Legally independent subsidiaries protect sensitive data.

**Example:**

```
Holding AG (scope with include_descendants=true)
  ├── Branch Munich
  │   └── ✅ Holding HR sees employees (inherited)
  │
  └── Regional GmbH (blocks: employee.*)
      └── ❌ Holding HR blocked (legal boundary)
```

#### Database Schema

```php
// organizational_units table
Schema::table('organizational_units', function (Blueprint $table) {
    $table->jsonb('inheritance_blocks')->nullable()
        ->comment('JSONB: blocked permissions for GDPR compliance');
    $table->index('inheritance_blocks');  // GIN index
});

// JSON structure:
{
  "blocked_permissions": [
    "employee.read",
    "employee.update",
    "employee.delete",
    "employee_document.*",
    "employee_qualification.*"
  ],
  "reason": "Legally independent subsidiary - GDPR Article 5(1)(c)",
  "effective_date": "2025-12-21",
  "applies_to_descendants": true
}
```

#### Policy Logic

```php
public function view(User $user, Employee $employee): bool
{
    // 1. Permission check
    if (!$user->hasPermissionTo('employee.read')) {
        return false;
    }

    // 2. Leadership level check (see Section 2)
    if (!$this->canViewLeadershipLevel($user, $employee)) {
        return false;
    }

    // 3. Organizational scope check
    $unit = $employee->organizationalUnit;

    // 4. Check inheritance blocking
    if ($unit->blocksPermissionInheritance('employee.read')) {
        // Blocked → Only DIRECT scope allowed
        return $user->organizationalScopes()
            ->where('organizational_unit_id', $unit->id)
            ->exists();
    }

    // 5. Normal inheritance check
    return $user->hasAccessToUnit($unit);
}
```

### 2. Leadership-Based Access Control (Hierarchical Filtering)

**Concept:** Users can only view employees **below their own leadership rank**, preventing horizontal (peer) and upward (superior) access.

**Implementation:** Flexible, tenant-configurable leadership levels.

#### Database Schema

```php
// leadership_levels table (tenant-specific definitions)
Schema::create('leadership_levels', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignId('tenant_id')->constrained('tenant_keys')->cascadeOnDelete();

    $table->unsignedTinyInteger('rank')
        ->comment('Numerical hierarchy (1=CEO, ascending for lower levels)');

    $table->string('name', 100)
        ->comment('Display name (e.g., "Managing Director", "Site Manager")');

    $table->text('description')->nullable();
    $table->string('color', 7)->nullable()->comment('Hex color for UI');
    $table->boolean('is_active')->default(true);

    $table->timestamps();

    $table->unique(['tenant_id', 'rank']);
    $table->unique(['tenant_id', 'name']);
});

// employees table
Schema::table('employees', function (Blueprint $table) {
    $table->foreignUuid('leadership_level_id')
        ->nullable()
        ->after('position')
        ->constrained('leadership_levels')
        ->nullOnDelete()
        ->comment('Leadership level (null = no leadership)');

    $table->index(['tenant_id', 'leadership_level_id']);
});

// user_internal_organizational_scopes table
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    // Remove access_level enum (no longer needed)
    $table->dropColumn('access_level');

    // Add leadership level filters
    $table->unsignedTinyInteger('min_viewable_rank')
        ->nullable()
        ->comment('Minimum rank user can view (inclusive)');

    $table->unsignedTinyInteger('max_viewable_rank')
        ->nullable()
        ->comment('Maximum rank user can view (inclusive)');

    // null/null = all levels
    // 5/null = rank 5 and below (subordinates)
    // null/3 = rank 3 and above (superiors - rare case)
});
```

#### Example Leadership Levels (Tenant-Configurable)

**Small Company (KMU):**

```
Rank 1: Managing Director
Rank 2: Branch Director
Rank 3: Area Manager
Rank 4: Site Manager
```

**Large Corporation (Konzern):**

```
Rank 1: CEO
Rank 2: Regional CEO
Rank 3: Branch Director
Rank 4: Regional Area Manager
Rank 5: Area Manager
Rank 6: Operations Manager
Rank 7: Site Manager
Rank 8: Shift Supervisor
```

#### Access Control Logic

```php
class EmployeePolicy
{
    public function view(User $user, Employee $employee): bool
    {
        // ... permission & scope checks ...

        return $this->canViewLeadershipLevel($user, $employee);
    }

    private function canViewLeadershipLevel(User $user, Employee $employee): bool
    {
        $employeeRank = $employee->leadershipLevel?->rank;

        // Target employee has no leadership level (e.g., Guards)
        // → accessible to everyone with employee.read permission
        if ($employeeRank === null) {
            return true;
        }

        // Target employee HAS leadership level (e.g., Branch Director)
        // → check user's rank filters in their scopes
        $matchingScopes = $user->organizationalScopes()
            ->where(function($q) use ($employee) {
                // Scope includes employee's org unit
                $q->where('organizational_unit_id', $employee->organizational_unit_id)
                  ->orWhere(function($q) use ($employee) {
                      // Or scope with descendants covering this unit
                      $q->where('include_descendants', true)
                        ->whereIn('organizational_unit_id',
                            $employee->organizationalUnit->ancestorIds()
                        );
                  });
            })
            ->get();

        foreach ($matchingScopes as $scope) {
            $minRank = $scope->min_viewable_rank;
            $maxRank = $scope->max_viewable_rank;

            // Check if employee's rank is within allowed range
            $withinMin = $minRank === null || $employeeRank >= $minRank;
            $withinMax = $maxRank === null || $employeeRank <= $maxRank;

            if ($withinMin && $withinMax) {
                return true;
            }
        }

        return false;
    }
}
```

---

## Detailed Design

### Inheritance Blocking: Resource-Specific Control

**Wildcard Support:**

```json
{
  "blocked_permissions": [
    "employee.*", // All employee permissions
    "employee_document.*", // All document permissions
    "employee_contract.*" // All contract permissions
  ]
}
```

**Policy Check with Wildcards:**

```php
public function blocksPermissionInheritance(string $permission): bool
{
    $blocks = $this->inheritance_blocks ?? [];
    $blockedPerms = $blocks['blocked_permissions'] ?? [];

    foreach ($blockedPerms as $blocked) {
        // Exact match
        if ($blocked === $permission) {
            return true;
        }

        // Wildcard match (resource.*)
        if (str_ends_with($blocked, '.*')) {
            $blockedResource = substr($blocked, 0, -2);
            $permissionResource = explode('.', $permission)[0];

            if ($blockedResource === $permissionResource) {
                return true;
            }
        }
    }

    return false;
}
```

### Leadership Levels: Tenant-Specific Configuration

**Standard Names with Translation:**

```php
// lang/en/leadership.php
return [
    'Managing Director' => 'Managing Director',
    'Branch Director' => 'Branch Director',
    'Area Manager' => 'Area Manager',
    'Site Manager' => 'Site Manager',
    // CEO, CFO, COO not included - they're international!
];

// lang/de/leadership.php
return [
    'Managing Director' => 'Geschäftsführer',
    'Branch Director' => 'Niederlassungsleiter',
    'Area Manager' => 'Bereichsleiter',
    'Site Manager' => 'Standortleiter',
];
```

**Helper for Translation:**

```php
class LeadershipLevelHelper
{
    public static function translateName(string $name, ?string $locale = null): string
    {
        $locale = $locale ?? app()->getLocale();
        $translated = __('leadership.' . $name, [], $locale);

        // Fallback to original if no translation exists
        return $translated === 'leadership.' . $name ? $name : $translated;
    }
}
```

**Management RBAC:**

Only users with **Rank 1** (or no rank - dedicated admins) can **create** new leadership levels.

All users can **edit** levels below their own rank.

```php
class LeadershipLevelPolicy
{
    public function create(User $user): bool
    {
        if (!$user->hasPermissionTo('tenant.manage_settings')) {
            return false;
        }

        $userRank = $user->employee?->leadershipLevel?->rank;
        return $userRank === null || $userRank === 1;
    }

    public function update(User $user, LeadershipLevel $level): bool
    {
        if (!$user->hasPermissionTo('tenant.manage_settings')) {
            return false;
        }

        $userRank = $user->employee?->leadershipLevel?->rank;

        // Rank 1 or no rank = full access
        if ($userRank === null || $userRank === 1) {
            return true;
        }

        // Others can only edit levels below their rank
        return $level->rank > $userRank;
    }
}
```

---

## Real-World Examples

### Example 1: Area Manager with Peer Isolation

**Setup:**

```php
// Employees
Employee "Hans Weber" (Area Manager Operations):
  organizational_unit_id: "niederlassung-berlin"
  leadership_level_id: "rank-5"  // Rank 5

Employee "Klaus Müller" (Area Manager Security):
  organizational_unit_id: "niederlassung-berlin"
  leadership_level_id: "rank-5"  // Rank 5 (peer!)

Employee "Peter Schmidt" (Site Manager):
  organizational_unit_id: "niederlassung-berlin"
  leadership_level_id: "rank-6"  // Rank 6 (subordinate)

// User Scope
User "hans.weber@company.de":
  Scope:
    organizational_unit_id: "niederlassung-berlin-operations"
    include_descendants: true
    min_viewable_rank: 6  // Only rank 6 and below!
    max_viewable_rank: null

  Permissions:
    - employee.read
    - employee.update
```

**Result:**

- ✅ Hans sees Peter Schmidt (rank 6 - subordinate)
- ✅ Hans sees Guards (no rank - subordinates)
- ❌ Hans does NOT see Klaus Müller (rank 5 - peer, outside min_viewable_rank)
- ❌ Hans does NOT see Branch Director (rank 3 - superior)

### Example 2: Regional GmbH with Inheritance Blocking

**Setup:**

```php
// Organizational Structure
OrganizationalUnit "Holding AG":
  parent_id: null
  inheritance_blocks: null

OrganizationalUnit "Regional GmbH":
  parent_id: "holding-ag-id"
  inheritance_blocks: {
    "blocked_permissions": ["employee.*", "employee_document.*"],
    "reason": "Legally independent subsidiary - GDPR compliance",
    "applies_to_descendants": true
  }

// Users
User "petra.schmidt@holding.de" (Holding HR):
  Scope:
    organizational_unit_id: "holding-ag-id"
    include_descendants: true  // Includes Regional GmbH!

  Permissions:
    - employee.read
    - employee.update

User "maria.meier@regional-gmbh.de" (Regional GmbH HR):
  Scope:
    organizational_unit_id: "regional-gmbh-id"
    include_descendants: true

  Permissions:
    - employee.read
    - employee.update
```

**Result:**

- ✅ Petra (Holding HR) sees Holding AG employees
- ❌ Petra blocked from Regional GmbH employees (inheritance blocked)
- ✅ Maria (Regional HR) sees Regional GmbH employees (direct scope)

### Example 3: Branch Director with Full Branch Access

**Setup:**

```php
// Employee
Employee "Thomas Müller" (Branch Director):
  organizational_unit_id: "niederlassung-berlin"
  leadership_level_id: "rank-3"  // Rank 3

// User Scope
User "thomas.mueller@company.de":
  Scope:
    organizational_unit_id: "niederlassung-berlin"
    include_descendants: true
    min_viewable_rank: 4  // Rank 4 and below
    max_viewable_rank: null

  Permissions:
    - employee.read
    - employee.update
```

**Result:**

- ✅ Thomas sees Area Managers (rank 5)
- ✅ Thomas sees Site Managers (rank 6)
- ✅ Thomas sees all Guards (no rank)
- ❌ Thomas does NOT see Regional CEO (rank 2 - superior)
- ❌ Thomas does NOT see peer Branch Directors (rank 3 - not within min_viewable_rank)

---

## Migration from access_level Enum

### Before (ADR-007 Original)

```php
user_internal_organizational_scopes:
  - access_level: enum('none', 'read', 'write', 'manage', 'admin')
  - include_descendants: boolean
```

**Problems:**

- "admin" level was vague (admin of what?)
- "manage" vs "admin" distinction unclear
- Not granular enough for leadership hierarchies

### After (This ADR)

```php
user_internal_organizational_scopes:
  - include_descendants: boolean
  - min_viewable_rank: int (nullable)
  - max_viewable_rank: int (nullable)

// Access control now via:
// 1. Spatie Permissions (what actions)
// 2. Organizational Scopes (which units)
// 3. Leadership Rank Filters (which levels)
```

**Advantages:**

- ✅ Clear separation: Permissions (what) vs. Scopes (where) vs. Levels (who)
- ✅ Fine-grained control: Rank ranges
- ✅ Flexible: Tenant defines own levels
- ✅ No special "admin" concept

### Migration Strategy

```php
// Migration: Remove access_level, add rank filters
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    $table->dropColumn('access_level');
    $table->unsignedTinyInteger('min_viewable_rank')->nullable();
    $table->unsignedTinyInteger('max_viewable_rank')->nullable();
});

// Data Migration Logic
UserInternalOrganizationalScope::where('access_level', 'admin')->each(function ($scope) {
    // Former "admin" → Full access (all ranks)
    $scope->update([
        'min_viewable_rank' => null,
        'max_viewable_rank' => null,
    ]);

    // Ensure user has appropriate permissions
    $scope->user->givePermissionTo('employee.read');
});
```

---

## Security Considerations

### Defense-in-Depth: Multiple Validation Layers

**1. Request Validation:**

- Validates inheritance block structure
- Validates leadership rank ranges
- Prevents SQL injection via regex validation

**2. Policy Authorization:**

- Checks permissions (`employee.read`, `employee.update`, etc.)
- Checks organizational scopes
- Checks inheritance blocking
- Checks leadership rank filters

**3. Model Layer:**

- Foreign key constraints
- Unique constraints (tenant_id, rank)
- Cascade delete protection

### Privilege Escalation Prevention

**Scenario: Child Admin Attempts Parent Access**

```php
// Attempted attack
POST /employees
Authorization: Bearer <child-admin-token>
// Query attempts to access parent org employees

// Prevention
EmployeePolicy::viewAny():
  1. Get user's organizational scopes
  2. Query filtered to accessible units only
  3. Inheritance blocks checked
  4. Leadership rank filters applied
  → Parent org employees not in accessible units → denied
```

**Scenario: Peer Access Attempt**

```php
// Area Manager Operations attempts to view Area Manager Security

// Prevention
EmployeePolicy::view():
  1. Permission check: employee.read ✓
  2. Scope check: Same org unit ✓
  3. Leadership rank check:
     - Target rank: 5 (peer)
     - min_viewable_rank: 6 (only subordinates)
     → Rank 5 < 6 → denied
```

### Audit Trail

**Inheritance Block Changes:**

```php
// Log in audit_logs table
[
    'action' => 'inheritance_block_modified',
    'organizational_unit_id' => $unit->id,
    'blocked_permissions' => ['employee.*'],
    'modified_by' => $user->id,
    'reason' => $request->input('reason'),
    'timestamp' => now(),
]
```

**Leadership Level Management:**

```php
[
    'action' => 'leadership_level_created',
    'leadership_level_id' => $level->id,
    'rank' => 5,
    'name' => 'Area Manager',
    'created_by' => $user->id,
    'timestamp' => now(),
]
```

---

## Implementation Plan

### Phase 1: Leadership Levels Infrastructure (2-3 weeks)

**Tasks:**

1. Create `leadership_levels` table
2. Add `leadership_level_id` to `employees` table
3. Create CRUD API for leadership levels
4. Implement translation support
5. Create seeder with default levels
6. Add validation & policies
7. Write comprehensive tests

**Testing:**

- [ ] CRUD operations work
- [ ] Tenant isolation (no cross-tenant access)
- [ ] Translation fallback works
- [ ] Rank uniqueness enforced
- [ ] RBAC: Only rank 1 can create levels

### Phase 2: Scope Rank Filters (2 weeks)

**Tasks:**

1. Remove `access_level` column from scopes
2. Add `min_viewable_rank` and `max_viewable_rank`
3. Update scope assignment UI/API
4. Modify `Employee` queries to filter by rank
5. Update policies with rank checks
6. Migrate existing scopes
7. Write comprehensive tests

**Testing:**

- [ ] Rank filters work correctly
- [ ] Null values handled (all ranks)
- [ ] Peer access blocked
- [ ] Subordinate access allowed
- [ ] Migration doesn't break existing scopes

### Phase 3: Inheritance Blocking (2-3 weeks)

**Tasks:**

1. Add `inheritance_blocks` JSONB column
2. Implement blocking check methods
3. Update all policies with block checks
4. Create UI for managing blocks
5. Add wildcard support
6. Write comprehensive tests

**Testing:**

- [ ] Blocks work for exact permissions
- [ ] Wildcards work (employee.\*)
- [ ] Direct scope overrides block
- [ ] applies_to_descendants works
- [ ] Performance acceptable

### Phase 4: UI & Documentation (1 week)

**Tasks:**

1. Leadership levels management UI
2. Scope assignment UI with rank filters
3. Inheritance blocking UI
4. Update user documentation
5. Create training materials
6. Migration guide

---

## Consequences

### Positive

**1. GDPR Compliance:**

- ✅ Need-to-Know principle enforced
- ✅ Legal entity boundaries respected
- ✅ Audit trail for data access

**2. Hierarchical Control:**

- ✅ Peers cannot view each other's HR data
- ✅ Subordinates visible, superiors hidden
- ✅ Flexible tenant-specific hierarchies

**3. Simplified Architecture:**

- ✅ No "admin" vs "super-admin" confusion
- ✅ Clear permission model (Permissions + Scopes + Levels)
- ✅ No "breaking glass" complexity

**4. Flexibility:**

- ✅ Tenant defines own leadership levels
- ✅ Levels can be added/removed dynamically
- ✅ Resource-specific blocking

### Negative

**1. Migration Effort:**

- ⚠️ Existing scopes must be migrated
- ⚠️ Training required for new concepts

**2. Complexity:**

- ⚠️ Three-dimensional access control (Permissions × Scopes × Levels)
- ⚠️ Rank filter configuration needed

**Mitigation:**

- Good documentation with examples
- UI helpers for common scenarios
- Migration scripts with defaults

---

## Related ADRs

- **ADR-005:** RBAC Design Decisions (permission system foundation)
- **ADR-007:** Organizational Structure Hierarchy (scope system)
- **ADR-008:** User-Based Tenant Resolution (tenant isolation)

---

## References

### Legal & Compliance

- **GDPR Article 5(1)(c):** Data minimization
- **GDPR Article 32:** Security of processing
- **ISO/IEC 27001:2013:** Access control

### Internal

- [Feature Requirements - Employee Management](../../feature-requirements.md#employee-management)
- [ADR Template](./template.md)

---

## Approval

**Author:** @kevalyq
**Date:** 2025-12-21

**Review Required By:**

- [ ] Security Team Lead
- [ ] Data Protection Officer (DPO)
- [ ] CTO / Technical Architect

**Approval Status:** Pending Review
