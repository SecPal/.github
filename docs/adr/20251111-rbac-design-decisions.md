<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-005: RBAC Design Decisions

**Status:** Accepted

**Date:** 2025-11-11

**Last Updated:** 2025-12-21 (ADR-009: Leadership-Based Access Control)

**Deciders:** @kevalyq

## Context

The SecPal RBAC system (Issue #5) required fundamental architectural decisions about role mutability, permission assignment patterns, and temporal access control. These decisions emerged during Phase 4 planning (Issue #108) and affect how the system handles role lifecycle, exceptional access cases, and time-limited permissions.

### Requirements That Drove These Decisions

1. **Flexibility:** Organizations must be able to adapt roles without system limitations
2. **Simplicity:** Rules should be consistent and easy to understand
3. **Exceptional Access:** System must handle edge cases without creating one-off roles
4. **Temporal Access:** Support time-limited permissions for compliance and operations
5. **Maintainability:** Avoid artificial complexity that creates confusion

## Decisions

### Decision 1: No System Roles - All Roles Equal

**Decision:** Do not implement an `is_system_role` flag or similar protection mechanism. All roles in the system are equal and follow identical rules for modification and deletion.

**Context:**

During RBAC design, we considered protecting predefined roles (Admin, Manager, Guard, Client, Works Council) from deletion or modification. Common patterns include:

- `is_system_role` boolean flag
- `protected` boolean flag
- Hardcoded role name checks in business logic
- Separate tables for system vs custom roles

**Our Approach:**

```php
// Single, unified deletion rule applies to ALL roles
public function destroy(Role $role)
{
    if ($role->users()->count() > 0) {
        throw ValidationException::withMessages([
            'role' => 'Cannot delete role while assigned to users'
        ]);
    }

    $role->delete(); // Works for Admin, Manager, Custom, any role
}
```

**Predefined Roles via Idempotent Seeder:**

```php
class RolesAndPermissionsSeeder extends Seeder
{
    public function run(): void
    {
        // Creates if not exists, skips if exists
        $admin = Role::firstOrCreate(
            ['name' => 'Admin', 'guard_name' => 'sanctum'],
            ['description' => 'Full system access']
        );

        // Sync permissions only if role has none
        if ($admin->permissions()->count() === 0) {
            $admin->syncPermissions(['*']);
        }

        // Repeat for Manager, Guard, Client, Works Council
    }
}
```

**Key Properties:**

- Predefined roles are created by seeder, not protected at runtime
- If role deleted, next seeder run recreates it
- All roles can be renamed, have permissions changed, or be deleted (if unassigned)
- Protection through assignment status, not artificial flags

**Rationale:**

1. **Simplicity:** One rule for all roles eliminates special cases
2. **Flexibility:** Organizations can modify everything via UI/API
3. **No Confusion:** No need to explain "system vs custom" distinction to users
4. **Maintainability:** Less code, fewer conditional branches, simpler testing
5. **Idempotent Recovery:** Deleted predefined roles automatically recreated

**Trade-offs:**

- Predefined roles can be accidentally deleted (mitigated by seeder)
- No visual distinction in UI between predefined and custom (acceptable)
- Requires running seeder after accidental deletion (acceptable operational overhead)

### Decision 2: Direct Permissions Independent of Roles

**Decision:** Users can have permissions assigned directly, bypassing the role system entirely. Direct permissions work independently and persist even when roles are removed.

**Permission Hierarchy:**

```
User Permissions = Role Permissions ∪ Direct Permissions
```

**Example:**

```
User "Alice" has role "Manager":
  - Role permissions: [employees.read, employees.update, shifts.*]
  - Direct permissions: [employees.export, reports.generate]
  - Total permissions: [employees.read, employees.update, shifts.*,
                        employees.export, reports.generate]

If "Manager" role removed:
  - Role permissions: [] (empty)
  - Direct permissions: [employees.export, reports.generate] (unchanged)
  - Total permissions: [employees.export, reports.generate]
```

**Use Cases:**

| Scenario                            | Solution                             | Why Direct Permission?                          |
| ----------------------------------- | ------------------------------------ | ----------------------------------------------- |
| Guard needs temporary export access | Assign `employees.export` for 1 week | Avoid modifying Guard role or creating new role |
| Manager should NOT delete employees | Revoke `employees.delete`            | Override role permission without role change    |
| Client needs report generation      | Assign `reports.generate`            | Special exception for one client only           |
| Auditor needs read access           | Assign multiple read permissions     | Time-limited access without "Auditor" role      |

**Implementation:**

Direct permissions use Spatie's `model_has_permissions` pivot table with optional temporal extensions:

```php
model_has_permissions:
  - model_type, model_id (user)
  - permission_id
  - valid_from (timestamp, nullable)     // Optional temporal
  - valid_until (timestamp, nullable)    // Optional temporal
```

**Rationale:**

1. **Flexibility for Edge Cases:** Handle exceptional access without role proliferation
2. **Reduced Role Complexity:** Avoid creating single-use or nearly-duplicate roles
3. **Clear Separation:** Roles for standard patterns, direct permissions for exceptions
4. **Temporal Support:** Direct permissions can also be time-limited
5. **Independence:** Changing roles doesn't affect direct permissions

**Trade-offs:**

- More complex permission checking logic (union of two sources)
- Requires careful UI design to show both permission types clearly
- Can be misused if overused (should be exceptional, not standard practice)

### Decision 3: Temporal Assignments Are Optional

**Decision:** Role and permission assignments are **permanent by default**. Temporal constraints (`valid_from`, `valid_until`) are optional features used only when time-limited access is explicitly required.

**Default Behavior:**

```php
// Permanent assignment (default - most common case)
POST /v1/users/{id}/roles
{
  "role": "manager"
  // No valid_from, no valid_until = permanent
}

// Temporal assignment (optional - special cases)
POST /v1/users/{id}/roles
{
  "role": "manager",
  "valid_from": "2025-12-01T00:00:00Z",
  "valid_until": "2025-12-14T23:59:59Z",
  "reason": "Vacation coverage for Manager A"
}
```

**When to Use Temporal:**

| Use Case           | Duration      | Approach                 | Expiration  |
| ------------------ | ------------- | ------------------------ | ----------- |
| Permanent employee | Indefinite    | Permanent role           | None        |
| Vacation coverage  | 1-2 weeks     | Temporal role            | Auto-revoke |
| Project access     | Weeks-months  | Temporal role/permission | Auto-revoke |
| Event elevation    | Hours-days    | Temporal role            | Auto-revoke |
| Compliance testing | Minutes-hours | Temporal permission      | Auto-revoke |

**Rationale:**

1. **Permanent is Common:** 80%+ of role assignments are indefinite
2. **Explicit Opt-in:** Temporal adds complexity (tracking, notifications, expiration)
3. **Clear Intent:** Nullable timestamps signal "this is special"
4. **Prevents Over-engineering:** Don't force temporal on everything
5. **Matches Real Usage:** Most employees have stable, long-term roles

**Trade-offs:**

- Need to remember to use temporal for time-limited access (not automatic)
- Requires expiration command running via scheduler
- Edge case: role expires during active user session (handled by scope filtering)

## Consequences

### Positive

1. **Simplicity:** Unified rules reduce cognitive load and code complexity
2. **Flexibility:** Organizations can adapt system to their needs
3. **Maintainability:** Less special-case code, fewer conditional branches
4. **Clarity:** Clear distinction between standard patterns (roles) and exceptions (direct)
5. **Recovery:** Idempotent seeder provides automatic recovery mechanism
6. **Scalability:** Simple rules scale better as system grows
7. **Testing:** Fewer edge cases to test

### Negative

1. **Accidental Deletion Risk:** Predefined roles can be deleted (mitigated by seeder)
2. **Permission Complexity:** Union of role + direct permissions requires careful implementation
3. **UI Challenge:** Must clearly show both permission sources to users
4. **Temporal Misuse Risk:** Developers might forget to use temporal for time-limited access
5. **Documentation Need:** Must document when to use direct vs role permissions

## Implementation Notes

### Database Schema

```sql
-- Roles table (Spatie provided)
roles:
  - id, name, guard_name
  - created_at, updated_at

-- Permissions table (Spatie provided)
permissions:
  - id, name, guard_name
  - created_at, updated_at

-- User-Role pivot (Spatie + temporal extensions)
model_has_roles:
  -- Spatie columns
  - model_type, model_id, role_id, team_id
  -- Temporal extensions
  + valid_from (timestamp nullable)
  + valid_until (timestamp nullable)
  + auto_revoke (boolean default true)
  + assigned_by (uuid nullable)
  + reason (text nullable)
  + created_at, updated_at

-- User-Permission pivot (Spatie + optional temporal)
model_has_permissions:
  -- Spatie columns
  - model_type, model_id, permission_id, team_id
  -- Optional temporal extensions
  + valid_from (timestamp nullable)
  + valid_until (timestamp nullable)
```

### Permission Naming Convention

Format: `resource.action`

**Resources:** `employees`, `shifts`, `work_instructions`, `roles`, `permissions`, `works_council`, `reports`

**Common Actions:** `read`, `create`, `update`, `delete`, `export`, `*` (wildcard)

**Special Actions:**

- `employees.read_salary` - View salary data
- `employees.read_all_branches` - Cross-branch access
- `shifts.approve_as_br` - Works council approval
- `roles.assign_temporary` - Assign temporal roles

### Active Role Filtering

```php
// Eloquent scope ensures only valid roles are considered
public function scopeActive($query)
{
    return $query->where(function ($q) {
        $q->whereNull('valid_from')
          ->orWhere('valid_from', '<=', now());
    })->where(function ($q) {
        $q->whereNull('valid_until')
          ->orWhere('valid_until', '>', now());
    });
}
```

### Expiration Command

```php
// Console/Commands/ExpireRoles.php
// Scheduled via: Schedule::command('roles:expire')->everyMinute();

public function handle()
{
    $expired = DB::table('model_has_roles')
        ->where('auto_revoke', true)
        ->where('valid_until', '<', now())
        ->get();

    foreach ($expired as $assignment) {
        // Delete assignment
        DB::table('model_has_roles')
            ->where('model_id', $assignment->model_id)
            ->where('role_id', $assignment->role_id)
            ->delete();

        // Log to audit trail
        RoleAssignmentLog::create([
            'user_id' => $assignment->model_id,
            'role_id' => $assignment->role_id,
            'action' => 'expired',
            // ...
        ]);
    }
}
```

## Alternatives Considered

### Alternative 1: Protected System Roles

**Approach:** Implement `is_system_role` flag to prevent deletion/modification of predefined roles.

**Rejected because:**

- Creates two-tier system with confusing rules
- Requires special-case logic throughout codebase
- Limits organizational flexibility unnecessarily
- Idempotent seeder provides equivalent protection with more flexibility

### Alternative 2: Role-Only Permissions (No Direct)

**Approach:** Force all permissions through roles, create custom roles for exceptions.

**Rejected because:**

- Leads to role proliferation (many single-use roles)
- Harder to manage exceptional cases
- More complex for temporary special access
- Creates confusion about which role to use

### Alternative 3: Temporal by Default

**Approach:** Make all role assignments require expiration dates.

**Rejected because:**

- Most assignments are permanent (forces unnecessary work)
- Confusing to set "expires in 100 years" for permanent roles
- Adds complexity where not needed
- Breaks principle of least surprise

## Related

- **Issue #5:** RBAC System (parent issue)
- **Issue #108:** RBAC Phase 4 (implementation)
- **Issues #137-140:** Phase 4 sub-issues
- **ADR-004:** RBAC Architecture (Spatie + Temporal Extensions)
- **ADR-007:** Organizational Structure Hierarchy (organizational scopes)
- **ADR-009:** Permission Inheritance Blocking & Leadership-Based Access Control (extends RBAC with hierarchical access)
- **PRs #109, #112, #113:** Phase 1 (temporal extensions)
- **PRs #117, #118, #120:** Phase 2 (expiration logic)
- **PR #121:** Phase 3 (API endpoints)

### Leadership-Based Access Control (See ADR-009)

This ADR establishes the foundation for role-based access control. **No role has default privileges** - all roles (including "Admin") are equal and access is controlled exclusively through:

1. **Permissions:** Spatie Laravel-Permission system (e.g., `employee.read`, `employee.update`)
2. **Organizational Scopes:** Access to specific organizational units (ADR-007)
3. **Leadership Level Filters:** Rank-based visibility control (ADR-009)

**Note:** The "Admin" role is a regular role name without special meaning to the system. It typically receives broad permissions via the seeder, but can be modified, deleted, or renamed like any other role.

ADR-009 extends this with:

- **Leadership Levels:** Tenant-configurable hierarchical ranks (1=CEO, ascending)
- **Horizontal Access Control:** Users cannot view peers or superiors
- **Inheritance blocking:** Child organizational units can block permission inheritance from parent units
- **Defense-in-depth:** Multiple validation layers prevent privilege escalation

Direct permissions (Decision 2) can be restricted by organizational unit inheritance blocks, providing resource-specific access control aligned with GDPR need-to-know principles.

## References

- [Spatie Laravel-Permission](https://spatie.be/docs/laravel-permission)
- [Principle of Least Privilege](https://en.wikipedia.org/wiki/Principle_of_least_privilege)
- [RBAC Wikipedia](https://en.wikipedia.org/wiki/Role-based_access_control)
- SecPal API Issue #5: RBAC System
- SecPal API Issue #108: RBAC Phase 4
