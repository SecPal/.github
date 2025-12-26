<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-009: Permission Inheritance Blocking & Leadership-Based Access Control

## Status

**Partially Superseded by [ADR-011](20251227-simplify-management-level-to-integer-field-adr011.md)** (Management level implementation changed)

**Proposed** (Draft - awaiting review for permission inheritance blocking)

## Date

2025-12-21

**Last Updated:** 2025-12-27 (Management level implementation updated)

## Context

**⚠️ NOTE:** This ADR originally described a `leadership_levels` table with LeadershipLevel model. Epic #399 simplified this to a direct `management_level` integer field (0-255) on the `employees` table. See [ADR-011](20251227-simplify-management-level-to-integer-field-adr011.md) for the current implementation. The organizational scope filtering logic described in this ADR remains **unchanged**.

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

**Implementation:** Simple integer-based management levels (0-255).

#### Database Schema

**⚠️ UPDATED (2025-12-27):** The original design used a separate `leadership_levels` table. This was simplified in Epic #399 to a direct `management_level` field. See [ADR-011](20251227-simplify-management-level-to-integer-field-adr011.md) for details.

```php
// employees table (simplified in Epic #399)
Schema::create('employees', function (Blueprint $table) {
    // ...
    $table->unsignedTinyInteger('management_level')
        ->default(0)
        ->nullable(false)
        ->comment('Management level: 0=non-management, 1=CEO/highest, 2-255=lower levels');
    // ...

    $table->index(['tenant_id', 'management_level']);
});

// user_internal_organizational_scopes table (UNCHANGED)
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    // Remove access_level enum (no longer needed)
    $table->dropColumn('access_level');

    // Add management level filters for VIEWING
    $table->unsignedTinyInteger('min_viewable_rank')
        ->nullable()
        ->comment('Minimum rank user can view (inclusive, null = no minimum)');

    $table->unsignedTinyInteger('max_viewable_rank')
        ->nullable()
        ->comment('Maximum rank user can view (inclusive, null/0 = only employees without management)');

    // Add management level filters for ASSIGNING (used in Operation 2)
    $table->unsignedTinyInteger('min_assignable_rank')
        ->nullable()
        ->comment('Minimum rank user can assign to employees (null = no minimum)');

    $table->unsignedTinyInteger('max_assignable_rank')
        ->nullable()
        ->comment('Maximum rank user can assign to employees (null/0 = cannot assign any management level)');

    // 🔒 NEW: Self-access control flag
    $table->boolean('allow_self_access')
        ->default(false)
        ->comment('Whether user can view/edit their own HR data via this scope');

    $table->index(['min_viewable_rank', 'max_viewable_rank']);
    $table->index(['min_assignable_rank', 'max_assignable_rank']);

    // Examples for viewable_rank (SEMANTICS UNCHANGED):
    // null/null or 0/0 = ONLY employees without management (no Führungskräfte)
    // 5/null or 5/0 = INVALID: min=5 (only ML5+) intersects with max=null/0 (only non-management) → no employees visible
    // 1/255 = can view ALL management ranks (ML1 through ML255), NOT non-management
    // null/2 or 0/2 = can view management ranks ML1–ML2 (no minimum restriction, max=2)
    // 3/255 = can view rank 3 and all numerically higher ranks (ML3, ML4, ..., ML255)
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

        return $this->canViewManagementLevel($user, $employee);
    }

    private function canViewManagementLevel(User $user, Employee $employee): bool
    {
        // UPDATED (2025-12-27): Direct field access instead of relationship
        $employeeRank = $employee->management_level;

        // Get user's scopes covering this employee's org unit
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

            // Target employee has NO management level (0 = non-management, e.g., Guards)
            if ($employeeRank === 0) {
                // Scopes with max_viewable_rank = null or 0 are **non-management-only**
                if ($maxRank === null || $maxRank === 0) {
                    // 🔒 SELF-ACCESS CHECK: Prevent users from accessing their own HR data
                    if ($employee->id === $user->employee->id && !$scope->allow_self_access) {
                        continue;  // User cannot access their own non-management data via this scope
                    }

                    return true;
                }
                continue;  // This scope doesn't allow non-management employees (only management with max >= 1)
            }

            // Target employee HAS management level (1-255, e.g., Branch Director)
            // null/0 in max_viewable_rank means "only non-management" → blocked
            if ($maxRank === null || $maxRank === 0) {
                continue;  // This scope doesn't allow management employees
            }

            // Check if employee's rank is within allowed range
            $withinMin = $minRank === null || $employeeRank >= $minRank;
            $withinMax = $employeeRank <= $maxRank;

            if ($withinMin && $withinMax) {
                // 🔒 SELF-ACCESS CHECK: Prevent users from accessing their own HR data
                // Only relevant if user's own rank is within the scope's range
                if ($employee->id === $user->employee->id) {
                    // Check if scope explicitly allows self-access
                    if (!$scope->allow_self_access) {
                        continue;  // User cannot access their own data via this scope
                    }
                }

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
    // Check current unit's blocks
    $blocks = $this->inheritance_blocks ?? [];
    $blockedPerms = $blocks['blocked_permissions'] ?? [];

    if ($this->hasBlockedPermission($blockedPerms, $permission)) {
        return true;
    }

    // Check ancestors with applies_to_descendants = true
    $ancestors = $this->ancestors()->get();

    foreach ($ancestors as $ancestor) {
        $ancestorBlocks = $ancestor->inheritance_blocks ?? [];
        $appliesToDescendants = $ancestorBlocks['applies_to_descendants'] ?? false;

        if ($appliesToDescendants) {
            $ancestorPerms = $ancestorBlocks['blocked_permissions'] ?? [];
            if ($this->hasBlockedPermission($ancestorPerms, $permission)) {
                return true;
            }
        }
    }

    return false;
}

protected function hasBlockedPermission(array $blockedPerms, string $permission): bool
{

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

### RBAC Architecture: Two Independent Operations

**⚠️ UPDATED (2025-12-27):** Operation 1 (LeadershipLevel CRUD) was **removed** in Epic #399. Management levels are now direct integer values (0-255) without a separate definition table. See [ADR-010](20251227-simplify-management-level-to-integer-field.md).

**CRITICAL:** Management levels have **NO inherent permission implications**. A user's own management level does NOT grant or restrict any permissions. All access control is explicit via Spatie permissions.

#### ~~Operation 1: Leadership Level Definition Management (CRUD)~~ [REMOVED]

**Status:** ❌ **Removed in Epic #399** (2025-12-27)

~~**What:** Creating/editing/deleting the leadership level definitions themselves (e.g., "Branch Director = Rank 3")~~

~~**Authorization:** Pure permission-based, **independent of user's own leadership level**~~

Management levels are now hardcoded as integers (0-255) with standard industry semantics:

- 0 = Non-management (Guards)
- 1 = CEO/Highest
- 2 = Branch Director
- 3-255 = Lower management tiers

No CRUD operations or policies needed—levels are assigned directly as integers.

#### Operation 2: Management Level Assignment to Employees (Renumbered: was Operation 2)

**What:** Assigning a management level to an employee (setting `employee.management_level`)

**Authorization:** Permission-based + **scope-based management level range check**

```php
class EmployeePolicy
{
    public function assignManagementLevel(User $user, Employee $employee, ?int $targetRank): bool
    {
        // 1. User needs permission to update employees
        if (!$user->hasPermissionTo('employee.update')) {
            return false;
        }

        // 2. User needs organizational scope access to employee
        if (!$user->hasAccessToUnit($employee->organizationalUnit)) {
            return false;
        }

        // 3. When REMOVING management (targetRank = 0), check current rank
        // UPDATED (2025-12-27): Direct field access instead of relationship
        if ($targetRank === 0 && $employee->management_level > 0) {
            // Must have permission to modify this employee's CURRENT rank
            // Prevents permission escalation: Can't demote CEO if you can't promote to CEO
            $currentRank = $employee->management_level;
            return $this->canAssignManagementRank($user, $employee, $currentRank);
        }

        // 4. When ASSIGNING management, check target rank
        if ($targetRank !== null && $targetRank > 0) {
            return $this->canAssignManagementRank($user, $employee, $targetRank);
        }

        // 5. Removing management from non-management employee (0 → 0) is always allowed
        return true;
    }

    private function canAssignManagementRank(User $user, Employee $employee, int $targetRank): bool
    {
        // Get user's scopes that cover this employee's organizational unit
        $applicableScopes = $user->organizationalScopes()
            ->where(function($q) use ($employee) {
                $q->where('organizational_unit_id', $employee->organizational_unit_id)
                  ->orWhere(function($q) use ($employee) {
                      $q->where('include_descendants', true)
                        ->whereIn('organizational_unit_id',
                            $employee->organizationalUnit->ancestorIds()
                        );
                  });
            })
            ->get();

        // Check if ANY scope allows assigning this rank
        foreach ($applicableScopes as $scope) {
            $minRank = $scope->min_assignable_rank;
            $maxRank = $scope->max_assignable_rank;

            // null/0 in max_assignable_rank means "only employees without leadership" → blocked
            if ($maxRank === null || $maxRank === 0) {
                continue;  // This scope cannot assign leadership levels
            }

            // Check if rank is within allowed range
            $withinMin = $minRank === null || $targetRank >= $minRank;
            $withinMax = $targetRank <= $maxRank;

            if ($withinMin && $withinMax) {
                return true;
            }
        }

        return false;
    }
}
```

**Database Schema Addition:**

```php
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    // For VIEWING employees with leadership levels
    $table->unsignedTinyInteger('min_viewable_rank')->nullable();
    $table->unsignedTinyInteger('max_viewable_rank')->nullable();

    // For ASSIGNING leadership levels to employees (NEW!)
    $table->unsignedTinyInteger('min_assignable_rank')->nullable()
        ->comment('Minimum rank user can assign to employees (inclusive)');
    $table->unsignedTinyInteger('max_assignable_rank')->nullable()
        ->comment('Maximum rank user can assign to employees (inclusive)');
});
```

**Examples:**

- ✅ User has scope with `min_assignable_rank = 3, max_assignable_rank = 255` → Can assign/remove ML3, ML4, ML5...
- ❌ User has scope with `max_assignable_rank = 2` → **Cannot** assign ML1 (superior) or remove ML1 from CEO
- ✅ User has scope with `min_assignable_rank = 1, max_assignable_rank = 255` → Can assign/remove all management ranks
- ❌ User has scope with `max_assignable_rank = null` or `= 0` → **Cannot** assign OR remove ANY management rank
- ⚠️ **CRITICAL:** To remove management level from employee, you must have permission to assign that level (prevents escalation!)

#### Operation 3: Permission Assignment with Management Level Filters (Renumbered: was Operation 3)

**What:** Granting permissions to other users with management level filters (setting scope's `min_viewable_rank/max_viewable_rank`)

**Authorization:** Permission-based + **rank range validation**

```php
class OrganizationalScopePolicy
{
    public function create(User $user): bool
    {
        return $user->hasPermissionTo('organizational_scope.create');
    }

    public function update(User $user, OrganizationalScope $scope): bool
    {
        return $user->hasPermissionTo('organizational_scope.update');
    }

    public function setManagementRangeFilter(
        User $user,
        ?int $minViewableRank,
        ?int $maxViewableRank
    ): bool {
        // 1. User needs permission to assign scopes
        if (!$user->hasPermissionTo('organizational_scope.update')) {
            return false;
        }

        // 2. Check if user can grant access to these ranks
        return $this->canGrantAccessToRankRange($user, $minViewableRank, $maxViewableRank);
    }

    private function canGrantAccessToRankRange(
        User $user,
        ?int $minViewableRank,
        ?int $maxViewableRank
    ): bool {
        // Get user's own maximum assignable rank across all scopes
        $userMaxAssignableRank = $user->organizationalScopes()
            ->max('max_assignable_rank');  // Highest max = least restrictive

        // User has no management assignment capability (null/0 = only non-management)
        if ($userMaxAssignableRank === null || $userMaxAssignableRank === 0) {
            // Can only grant access to non-management employees
            if ($maxViewableRank !== null && $maxViewableRank > 0) {
                return false;  // Trying to grant access to management ranks
            }
            return true;
        }

        // Check if target range is within user's assignable range
        // User with max_assignable_rank=2 can grant access to ML2 and numerically higher ranks (ML3, ML4, ...)
        if ($minViewableRank !== null && $minViewableRank < $userMaxAssignableRank) {
            return false;  // Trying to grant access to superior (higher-privilege, lower-number) ranks
        }

        if ($maxViewableRank !== null && $maxViewableRank > 0 && $maxViewableRank < $userMaxAssignableRank) {
            return false;  // Trying to include superior ranks in the viewable range via maxViewableRank
        }

        return true;
    }
}
```

**Examples:**

- ✅ User with `max_assignable_rank = 5` → Can grant scope with `min_viewable_rank = 5, max_viewable_rank = 255` (ML5 and below)
- ❌ User with `max_assignable_rank = 5` → **Cannot** grant scope with `min_viewable_rank = 1` (includes ML1-4)
- ❌ User with `max_assignable_rank = null` or `= 0` → Can **only** grant scope with `max_viewable_rank = null/0` (non-management only)
- ✅ User with `max_assignable_rank = 255` → Can grant any rank filter (including all management)

**⚠️ Invalid Combinations (Must be rejected during validation):**

These combinations are logically impossible and must be prevented by form validation:

- ❌ `min_viewable_rank = 5, max_viewable_rank = 0` → **INVALID**: No intersection between "ML5+" and "non-management only"
- ❌ `min_viewable_rank = 5, max_viewable_rank = null` → **INVALID**: Same as above
- ❌ `min_viewable_rank = 5, max_viewable_rank = 4` → **INVALID**: min > max (no management levels in range)
- ❌ `min_assignable_rank = 3, max_assignable_rank = 0` → **INVALID**: Same logic applies

**Validation Rule:**

```php
// StoreOrganizationalScopeRequest.php
public function rules(): array
{
    return [
        'min_viewable_rank' => 'nullable|integer|min:1',
        'max_viewable_rank' => [
            'nullable',
            'integer',
            function ($attribute, $value, $fail) {
                $minRank = $this->input('min_viewable_rank');

                // If max is 0/null AND min is set (> 0), that's invalid
                if ($minRank !== null && $minRank > 0) {
                    if ($value === null || $value === 0) {
                        $fail('Cannot combine management level filter (min_viewable_rank) with "non-management only" (max=0).');
                    }
                    if ($value < $minRank) {
                        $fail('max_viewable_rank must be greater than or equal to min_viewable_rank.');
                    }
                }
            }
        ],
        // Same validation for assignable ranks...
    ];
}
```

**Result:** User sees **NOBODY** with invalid combination - should be prevented at form submission!

**UI/UX Prevention Strategy:**

Instead of allowing users to enter `min` and `max` values directly (error-prone), the UI should guide them through **two independent yes/no questions**:

1. **"Should access to employees WITHOUT management level be allowed?"** → Sets `max_viewable_rank = 0`
2. **"Should access to employees WITH management level be allowed?"** → Activates range dropdowns
   - If YES: Select `min` (1-255) and `max` (≥min, ≤255)
   - Dropdowns automatically filter impossible values

This approach makes combinations like `min=5, max=0` **structurally impossible** to create in the UI.

**Backend must still validate** despite frontend UX, as API could be called directly.

### Summary: Own Management Level ≠ Permissions

**⚠️ UPDATED (2025-12-27):** Removed references to `leadership_level.*` permissions (no longer exist after Epic #399).

| User's Own ML | Permission                            | Can Do?                                                                  |
| ------------- | ------------------------------------- | ------------------------------------------------------------------------ |
| ML6           | `employee.update` + assignable scopes | ✅ Assign ML6-ML255 to employees within scopes                           |
| ML1           | No permission                         | ❌ Cannot update any employees                                           |
| `0` (no ML)   | `employee.create` + assignable scopes | ✅ Create employees with management levels within scope range            |
| ML6           | Scope with `max_assignable_rank=2`    | ❌ Cannot assign/remove ML1 to/from employees (only ML2+)                |
| ML6           | Scope with `max_assignable_rank=255`  | ✅ Can assign/remove ML1 to/from employees (all ranks)                   |
| ML6           | Scope with `max_assignable_rank=null` | ❌ Cannot assign/remove ANY management (only non-management)             |
| ML1           | Scope with `min=5, max=255`           | ❌ Cannot assign/remove ML2 to/from employees (outside range, only ML5+) |

---

## Real-World Examples

### Example 1: Area Manager with Peer Isolation

**⚠️ UPDATED (2025-12-27):** Changed from `leadership_level_id` to direct `management_level` field.

**Setup:**

```php
// Employees
Employee "Hans Weber" (Area Manager Operations):
  organizational_unit_id: "niederlassung-berlin"
  management_level: 5  // Rank 5

Employee "Klaus Müller" (Area Manager Security):
  organizational_unit_id: "niederlassung-berlin"
  management_level: 5  // Rank 5 (peer!)

Employee "Peter Schmidt" (Site Manager):
  organizational_unit_id: "niederlassung-berlin"
  management_level: 6  // Rank 6 (subordinate)

// User Scope
User "hans.weber@company.de":
  Scope:
    organizational_unit_id: "niederlassung-berlin-operations"
    include_descendants: true
    min_viewable_rank: 6  // Only rank 6 and below!
    max_viewable_rank: 255  // Can see all subordinate ranks
    max_assignable_rank: null  // Cannot assign leadership (only non-leadership)

  Permissions:
    - employee.read
    - employee.update
```

**Result:**

- ✅ Hans sees Peter Schmidt (rank 6 - subordinate)
- ❌ Hans does NOT see Guards (no rank - max_viewable_rank=255 only allows leadership, not non-leadership!)
- ❌ Hans does NOT see Klaus Müller (rank 5 - peer, outside min_viewable_rank)
- ❌ Hans does NOT see Branch Director (rank 3 - superior)

**Note:** To also see Guards (non-leadership), Hans would need a second scope with `max_viewable_rank = null/0`.

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
    max_viewable_rank: 255  // All subordinate ranks
    max_assignable_rank: 255  // Can assign all subordinate ranks

  Permissions:
    - employee.read
    - employee.update
```

**Result:**

- ✅ Thomas sees Area Managers (rank 5)
- ✅ Thomas sees Site Managers (rank 6)
- ❌ Thomas does NOT see Guards (no rank – this scope with max_viewable_rank = 255 only applies to leadership; non-leadership would require an additional scope with max_viewable_rank = null/0)
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
2. Scope assignment UI with rank filters (see detailed UX spec below)
3. Inheritance blocking UI
4. Update user documentation
5. Create training materials
6. Migration guide

**UI/UX Specification for Leadership Level Filters:**

The UI must guide users through a **two-step independent selection process** to prevent logically impossible combinations:

**Step 1: Non-Management Employees Access (Independent)**

```
☐ Allow access/editing of employees WITHOUT management level?
   (Allows access to employees without management level)
```

- If **checked** → Sets `max_viewable_rank = 0` (or `null`)
- If **unchecked** → No access to non-management employees
- **Independent** from management level filters (Step 2)

**Step 2: Management Level Range (Independent)**

```
☐ Allow access/editing of employees WITH management level?
   (Allows access to employees with management levels)

   ↳ From management level (min):  [Dropdown: ML1, ML2, ..., ML255]
   ↳ To management level (max):    [Dropdown: ML1, ML2, ..., ML255]

   Note: Lower rank number = Higher position
   (ML1 = CEO, ML255 = lowest management level)
```

- If **unchecked** → No access to management employees
- If **checked** → Dropdowns become active
  - `min_viewable_rank` dropdown: Only shows ranks ≤ user's `max_assignable_rank`
  - `max_viewable_rank` dropdown: Dynamically filtered based on selected `min`
  - **Validation:** If `min = 5` selected, `max` dropdown only shows `5, 6, 7, ..., 255`
  - **Prevents:** `min > max` combinations (logically impossible)

**🔒 Step 3: Self-Access Control (Conditional)**

This step is **only shown** if the user's own leadership level falls within the selected range from Step 2:

```
⚠️ Warning: This setting would allow the user to access their own personnel file!

☐ Allow user to access their own personnel file?
   (Allow user to view/edit their own HR data)

   ⚠️ Not recommended: Employees should normally not be able to edit their own
      salary data, contracts, or performance reviews.
```

- **Only visible if:** User's own `management_level` ∈ [`min_viewable_rank`, `max_viewable_rank`]
- **Default:** ☐ **Unchecked** (deny self-access for security)
- **If checked** → `allow_self_access = true` in scope
- **If unchecked** → `allow_self_access = false` (default, secure)

**When is this relevant?**

| User's ML | Scope Range            | Step 3 shown? | Reason                                        |
| --------- | ---------------------- | ------------- | --------------------------------------------- |
| ML3       | min=3, max=255         | ✅ YES        | User's rank (3) is in range [3-255]           |
| ML3       | min=5, max=255         | ❌ NO         | User's rank (3) is NOT in range [5-255]       |
| ML3       | min=1, max=2           | ❌ NO         | User's rank (3) is NOT in range [1-2]         |
| `0`       | max=0 (non-management) | ✅ YES        | User has no ML, scope allows non-management   |
| ML5       | max=0 (non-management) | ❌ NO         | User has ML, scope only allows non-management |

**Example 4: No access (both unchecked)**

- ☐ Step 1 unchecked
- ☐ Step 2 unchecked
- **Result:** Cannot see any employees in this scope (invalid, form should warn)

**UI Validation (Frontend):**

```javascript
// Prevent submission if both unchecked
if (!allowNonLeadership && !allowLeadership) {
  showError("At least one option must be selected.");
  return;
}

// Prevent min > max
if (allowLeadership && minRank > maxRank) {
  showError("Min rank must be ≤ max rank.");
  return;
}

// Prevent selecting ranks outside user's capability
if (maxRank < userMaxAssignableRank) {
  showError(
    `You are not allowed to grant access to management levels below ML${userMaxAssignableRank}.`
  );
  return;
}

// 🔒 Self-access validation: Only show/allow if user's rank in scope range
const targetUserRank = targetUser.leadership_level?.rank ?? null;
const scopeIncludesTargetUser =
  (targetUserRank === null && allowNonLeadership) ||
  (targetUserRank !== null &&
    allowLeadership &&
    targetUserRank >= minRank &&
    targetUserRank <= maxRank);

if (scopeIncludesTargetUser && !allowSelfAccessExplicitlySet) {
  showWarning(
    "This scope would allow the user to access their own data. Please confirm explicitly."
  );
}
```

**Backend Validation (Laravel):**

Despite frontend validation, backend MUST enforce all rules:

```php
// StoreOrganizationalScopeRequest.php
public function rules(): array
{
    return [
        'allow_non_leadership' => 'boolean',
        'allow_leadership' => 'boolean',
        'allow_self_access' => 'boolean',  // 🔒 NEW
        'min_viewable_rank' => [
            'nullable',
            'integer',
            'min:1',
            'required_if:allow_leadership,true',
            function ($attribute, $value, $fail) {
                if ($this->allow_leadership && $value === null) {
                    $fail('min_viewable_rank required when management levels are allowed.');
                }
            },
        ],
        'max_viewable_rank' => [
            'nullable',
            'integer',
            function ($attribute, $value, $fail) {
                // If non-leadership allowed, set to 0
                if ($this->allow_non_leadership && !$this->allow_leadership) {
                    if ($value !== 0 && $value !== null) {
                        $fail('max_viewable_rank must be 0 for non-management only.');
                    }
                }

                // If leadership allowed, validate range
                if ($this->allow_leadership) {
                    $minRank = $this->input('min_viewable_rank');

                    // Cannot be 0/null if leadership is allowed
                    if ($value === null || $value === 0) {
                        $fail('max_viewable_rank must be > 0 when management levels are allowed.');
                    }

                    // Min must be <= max
                    if ($minRank !== null && $value < $minRank) {
                        $fail('max_viewable_rank must be ≥ min_viewable_rank.');
                    }

                    // User cannot grant access to ranks they can't assign
                    $userMaxAssignable = auth()->user()->getMaxAssignableRank();
                    if ($userMaxAssignable !== null && $minRank < $userMaxAssignable) {
                        $fail("You are not allowed to grant access to management levels below ML{$userMaxAssignable}.");
                    }
                }

                // At least one must be allowed
                if (!$this->allow_non_leadership && !$this->allow_leadership) {
                    $fail('At least one option must be enabled.');
                }
            },
        ],
    ];
}
```

**Database Mapping:**

- `allow_non_leadership = true` → Store scope with `max_viewable_rank = 0`
- `allow_leadership = true, min = 5, max = 255` → Store scope with `min_viewable_rank = 5, max_viewable_rank = 255`
- Both checked → Store **TWO scopes** (one for non-leadership, one for leadership range)

**Same pattern applies to `assignable_rank` fields** (for permission granting)!

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
