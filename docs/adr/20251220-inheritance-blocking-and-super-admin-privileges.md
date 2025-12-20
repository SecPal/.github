<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-009: Permission Inheritance Blocking & Super-Admin Privileges

## Status

**Proposed** (Draft - awaiting review)

## Date

2025-12-20

## Context

### The Problem: GDPR Compliance in Complex Organizational Hierarchies

SecPal's organizational hierarchy system (ADR-007) allows creating complex multi-level structures representing holding companies, subsidiaries, branches, and divisions. However, the current permission inheritance model (`include_descendants = true/false`) creates a critical **GDPR compliance issue** when legally independent subsidiaries exist within the hierarchy.

#### Real-World Scenario: Holding with Subsidiaries

```
Holding AG (Root Organization)
├── HR Department (internal)
├── IT Department (internal)
├── Branch Munich (internal)
└── Regional GmbH (legally independent subsidiary)
    └── HR Department Regional
```

**Business Requirements:**

1. **Holding HR** needs access to:

   - ✅ Holding AG employee records
   - ✅ HR Department employee records
   - ✅ IT Department employee records
   - ✅ Branch Munich employee records
   - ❌ **Regional GmbH employee records** (GDPR violation: legally independent entity)

2. **Holding QM** needs access to:

   - ✅ Work instructions across ALL units (including Regional GmbH)
   - ❌ Employee records of Regional GmbH

3. **Regional GmbH** requirements:
   - ✅ Must have autonomous HR management
   - ✅ Must be able to appoint own administrators
   - ✅ Must protect employee data from parent organization
   - ✅ Holding super-admin must have emergency access (breaking glass principle)

#### Current System Limitations

**Problem 1: All-or-Nothing Inheritance**

```php
// Current approach: Multiple scopes required
UserInternalOrganizationalScope::create([
    'user_id' => $holdingHR->id,
    'organizational_unit_id' => $hrDepartment->id,
    'include_descendants' => true,
]);

UserInternalOrganizationalScope::create([
    'user_id' => $holdingHR->id,
    'organizational_unit_id' => $itDepartment->id,
    'include_descendants' => true,
]);

UserInternalOrganizationalScope::create([
    'user_id' => $holdingHR->id,
    'organizational_unit_id' => $branchMunich->id,
    'include_descendants' => false,
]);

// Regional GmbH: NO SCOPE (invisible)
```

**Issues:**

- ❌ Requires N scopes for N allowed units (management overhead)
- ❌ New branch/department requires updating all relevant scopes
- ❌ Regional GmbH is completely invisible (even for work instructions)
- ❌ Cannot differentiate between "no access" and "partial access"

**Problem 2: No Resource-Specific Inheritance**

Cannot say: "Inherit work instructions but NOT employee records"

**Problem 3: Admin Privilege Escalation Risk**

```php
// Dangerous: Regional admin could attempt:
POST /organizational-units/{holdingId}/scopes
{
  "user_id": "accomplice",
  "is_super_admin": true  // ← Try to gain super-admin for parent org!
}
```

**Problem 4: No Defense-in-Depth for Subsidiaries**

Child organizations cannot protect themselves from parent organization access.

### GDPR Legal Requirements

**Article 5(1)(c) - Data Minimization & Need-to-Know Principle:**

> Personal data shall be adequate, relevant and limited to what is necessary in relation to the purposes for which they are processed.

**Application to SecPal:**

- Holding HR has **no legitimate need** to access Regional GmbH employee records
- Regional GmbH is **legally independent** (separate legal entity)
- Employee data must be **isolated** by default
- Emergency access must be **audited** and **justified**

**Article 32 - Security of Processing:**

> Technical and organizational measures to ensure a level of security appropriate to the risk.

**Application to SecPal:**

- **Technical measure:** Inheritance blocking prevents unauthorized access
- **Organizational measure:** Super-admin restricted to root organization
- **Audit measure:** Emergency access logging (breaking glass)

---

## Decision

We implement **three interconnected security mechanisms** to solve the above problems:

### 1. Permission Inheritance Blocking (Defense-in-Depth)

**Concept:** Child organizational units can **block specific permissions** from being inherited from ancestor units, even when `include_descendants = true` is set on the ancestor scope.

**Approach:** "Pull model with blockade" instead of "push-only model"

```
Before (Push-only):
  Holding: "I push all permissions down!"
    ↓ ↓ ↓
  Branch: ✅ Accepts all
  Regional GmbH: ❌ Cannot refuse

After (Defense-in-Depth):
  Holding: "I offer all permissions!"
    ↓ ↓ ↓
  Branch: ✅ "I accept all"
  Regional GmbH: 🛡️ "I BLOCK employee.* permissions!"
```

#### Implementation

**Database Schema:**

```php
// organizational_units table
Schema::table('organizational_units', function (Blueprint $table) {
    $table->jsonb('inheritance_blocks')->nullable();
});

// JSON structure:
{
  "blocked_permissions": [
    "employee.read",
    "employee.update",
    "employee.delete",
    "employee_document.read",
    "employee_document.write",
    "employee_qualification.read"
  ],
  "blocked_access_levels": [
    "admin"  // Block admin-level access from ancestors
  ],
  "reason": "Legally independent subsidiary - GDPR Article 5(1)(c) compliance",
  "effective_date": "2025-12-20",
  "approved_by": "data_protection_officer",
  "allows_emergency_access": true,
  "emergency_requires_approval": true,
  "notify_on_emergency_access": [
    "dpo@regional-gmbh.com",
    "legal@regional-gmbh.com"
  ],
  "applies_to_descendants": true
}
```

**Policy Logic:**

```php
public function view(User $user, EmployeeDocument $document): bool
{
    $employee = $document->employee;
    $unit = $employee->organizationalUnit;

    // 1. Check if unit blocks this permission
    if ($unit->blocksPermissionInheritance('employee_document.read')) {
        // Inheritance blocked → Check only DIRECT scope
        return $user->organizationalScopes()
            ->where('organizational_unit_id', $unit->id)
            ->exists();
    }

    // 2. No block → Normal inheritance check
    return $user->hasAccessToUnit($unit);
}
```

### 2. Super-Admin Privileges (Root-Only)

**Concept:** Super-admin status can **only** be granted for root organizational units (units without parent) and **only** by existing root-unit super-admins.

**Security Rules:**

1. **Target Restriction:** Super-admin can only be assigned to root organizational units
2. **Granter Restriction:** Only super-admins with root-unit scope can grant super-admin
3. **Access Scope:** Super-admin can use breaking glass only for units within their scope or below (never upward)

#### Implementation

**Database Schema:**

```php
// user_internal_organizational_scopes table
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    $table->boolean('is_super_admin')->default(false);
});
```

**Policy Logic:**

```php
public function grantSuperAdmin(User $user, OrganizationalUnit $targetUnit): bool
{
    // Rule 1: Target must be root
    if ($targetUnit->parent_id !== null) {
        return false;
    }

    // Rule 2 & 3: Granter must be super-admin on root unit
    $hasRootSuperAdminScope = $user->organizationalScopes()
        ->where('is_super_admin', true)
        ->where('access_level', 'admin')
        ->whereHas('organizationalUnit', function ($q) {
            $q->whereNull('parent_id');
        })
        ->exists();

    if (!$hasRootSuperAdminScope) {
        return false;
    }

    // Rule 4: Must have admin access to target
    return $user->hasAccessToUnit($targetUnit, 'admin');
}
```

**Privilege Escalation Prevention:**

```php
public function canRequestEmergencyAccessTo(OrganizationalUnit $unit): bool
{
    $superAdminScopes = $this->organizationalScopes()
        ->where('is_super_admin', true)
        ->get();

    foreach ($superAdminScopes as $scope) {
        $scopeUnit = $scope->organizationalUnit;

        // Check: Is target unit an ANCESTOR? (upward access = FORBIDDEN)
        $isAncestor = OrganizationalUnitClosure::where('ancestor_id', $unit->id)
            ->where('descendant_id', $scopeUnit->id)
            ->where('depth', '>', 0)
            ->exists();

        if ($isAncestor) {
            return false;  // Prevent privilege escalation upward
        }
    }

    return true;
}
```

### 3. Breaking Glass Emergency Access

**Concept:** Super-admins can request time-limited emergency access to blocked resources, with full audit logging and optional approval workflow.

**Key Features:**

- ⏰ Time-limited (1-4 hours maximum)
- 📝 Mandatory justification
- 📊 Complete audit trail
- 🔔 Automatic notifications
- ✅ Optional 4-eyes approval
- 🚫 Cannot escalate upward (child-org admin cannot access parent)

#### Implementation

**Database Schema:**

```php
Schema::create('emergency_access_logs', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('user_id')->constrained()->cascadeOnDelete();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys')->cascadeOnDelete();
    $table->foreignUuid('organizational_unit_id')->nullable()
        ->constrained('organizational_units')->nullOnDelete();

    $table->string('resource_type');  // 'Employee', 'EmployeeDocument'
    $table->uuid('resource_id')->nullable();
    $table->string('action');  // 'view', 'update', 'delete'
    $table->string('permission');  // 'employee.read'

    $table->text('reason');  // Mandatory: WHY emergency access?
    $table->enum('urgency', ['low', 'medium', 'high', 'critical']);
    $table->timestamp('access_granted_at');
    $table->timestamp('access_expires_at');

    // Optional 4-eyes approval
    $table->foreignUuid('approved_by')->nullable()->constrained('users');
    $table->timestamp('approved_at')->nullable();

    // Audit: What was accessed?
    $table->json('accessed_fields')->nullable();
    $table->integer('access_count')->default(0);
    $table->timestamp('last_accessed_at')->nullable();
    $table->ipAddress('ip_address')->nullable();

    $table->timestamps();
    $table->index(['user_id', 'created_at']);
    $table->index(['organizational_unit_id', 'created_at']);
});
```

**Policy Integration:**

```php
public function view(User $user, EmployeeDocument $document): bool
{
    $employee = $document->employee;
    $unit = $employee->organizationalUnit;

    // 1. Check emergency access FIRST (highest priority)
    if ($this->hasActiveEmergencyAccess($user, 'employee_document.read', $unit)) {
        $this->logEmergencyAccess($user, $document);
        return true;
    }

    // 2. Admin check (NO default access to employee documents)
    if ($user->hasRole('Admin')) {
        return false;  // Admins need emergency access
    }

    // 3. Normal permission & scope checks
    // ...
}
```

---

## Detailed Design Decisions

### Decision 1: Inheritance Blocking at Unit Level (Not User Level)

**Why unit-level, not user-level?**

**Considered Alternatives:**

**A) User-level scope restrictions:**

```php
UserInternalOrganizationalScope::create([
    'user_id' => $user->id,
    'organizational_unit_id' => $holding->id,
    'include_descendants' => true,
    'scope_restrictions' => [
        'employee.read' => ['include_descendants' => false],
    ],
]);
```

**Rejected because:**

- ❌ Configuration burden: Every user with holding access needs restriction
- ❌ Error-prone: Forgetting restriction = data leak
- ❌ No organizational policy: Unit cannot protect itself
- ❌ Scales poorly: N users × M restrictions

**B) Separate permission-scope table:**

```php
user_permission_scopes:
  user_id, organizational_unit_id, permission_name, include_descendants
```

**Rejected because:**

- ❌ Over-engineering: Adds complexity without significant benefit
- ❌ Query performance: Additional JOIN for every permission check
- ❌ Management overhead: Separate UI for permission-level scopes

**C) Selected: Unit-level inheritance blocks:**

```php
organizational_units.inheritance_blocks:
  blocked_permissions, blocked_access_levels, reason, etc.
```

**Advantages:**

- ✅ **Organizational policy:** Unit defines its own protection
- ✅ **Self-documenting:** Clear why access is blocked
- ✅ **Fail-safe:** New users automatically respect blocks
- ✅ **Scalable:** One configuration protects from N users
- ✅ **Auditable:** Blocks are versioned with unit changes
- ✅ **Defense-in-depth:** Security at organizational level

### Decision 2: Super-Admin Restricted to Root Units

**Why root-only?**

**Security Rationale:**

1. **Prevent Horizontal Privilege Escalation:**

   - Child-org admin could grant super-admin to accomplice
   - Accomplice gains access to peer orgs at same level

2. **Prevent Upward Privilege Escalation:**

   - Child-org "super-admin" could use breaking glass upward
   - Subsidiary gains access to parent organization data

3. **Clear Security Boundary:**
   - Root = Highest privilege level
   - Child = Delegated authority within boundaries

**Considered Alternatives:**

**A) Super-admin for any unit:**

**Rejected because:**

- ❌ Ambiguous meaning: "Super" relative to what?
- ❌ Privilege escalation: Child could access parent
- ❌ Unclear hierarchy: Who can override whom?

**B) Hierarchical super-admin levels:**

```php
'super_admin_level' => [
    'root' => 4,      // Can access everything
    'division' => 3,  // Can access division + below
    'branch' => 2,    // Can access branch + below
]
```

**Rejected because:**

- ❌ Over-complex: Too many privilege levels
- ❌ Confusing: Users won't understand hierarchy
- ❌ Attack surface: More levels = more potential exploits

**C) Selected: Super-admin only for root units:**

**Advantages:**

- ✅ **Clear semantics:** "Super" means "across entire tenant"
- ✅ **Prevents escalation:** Cannot be granted by child-org admins
- ✅ **Auditable:** Small number of super-admins (typically 1-3)
- ✅ **Emergency-only:** Breaking glass, not daily operations

### Decision 3: Breaking Glass with Time Limits

**Why time-limited emergency access?**

**Security Principles:**

1. **Principle of Least Privilege:**

   - Access granted only when needed
   - Automatically revoked when no longer needed

2. **Principle of Accountability:**

   - All emergency access is logged
   - Reason must be documented
   - Cannot be done silently

3. **Principle of Minimization:**
   - Shortest duration necessary (1-4 hours)
   - Cannot grant permanent emergency access

**Considered Alternatives:**

**A) Permanent super-admin access to all data:**

**Rejected because:**

- ❌ GDPR violation: Need-to-Know principle
- ❌ No separation of duties: Admin = HR
- ❌ No audit trail: Normal operations not logged
- ❌ Insider threat: Permanent access to sensitive data

**B) Request-based access with approval (always required):**

**Rejected because:**

- ❌ Too slow: Emergency situations need immediate access
- ❌ Dependency: Requires approver availability (24/7?)
- ❌ Complexity: Approval workflow overhead

**C) Selected: Time-limited breaking glass with optional approval:**

**Advantages:**

- ✅ **Immediate access:** Available in emergencies
- ✅ **Self-limiting:** Automatically expires
- ✅ **Auditable:** Complete log of access
- ✅ **Flexible:** Can require approval for sensitive units
- ✅ **GDPR-compliant:** Legitimate interest + minimization

**Time Limits:**

- **Low urgency:** 1 hour (e.g., review audit log)
- **Medium urgency:** 2 hours (e.g., investigate issue)
- **High urgency:** 3 hours (e.g., security incident)
- **Critical urgency:** 4 hours (e.g., data recovery)
- **Maximum:** 4 hours (hard limit, cannot be extended without new request)

### Decision 4: Admin Role Has NO Default Access to Employee Documents

**Why separate Admin and HR?**

**Security Rationale:**

1. **Separation of Duties (SoD):**

   - **Admin role:** System configuration, user management, infrastructure
   - **HR role:** Employee records, payroll, personnel files
   - Different responsibilities = different access

2. **GDPR Need-to-Know:**

   - System admin has **no legitimate need** to view employee documents
   - Technical maintenance doesn't require personnel data access
   - Data minimization: Only HR should have access by default

3. **Insider Threat Mitigation:**
   - Admin has broad technical access (databases, backups, logs)
   - Limiting personnel data access reduces attack surface
   - Breaking glass provides emergency access with accountability

**Considered Alternatives:**

**A) Admin has full access to all data:**

**Rejected because:**

- ❌ GDPR violation: Excessive access
- ❌ No separation of duties
- ❌ Insider threat: Admin could abuse access silently

**B) Admin has read-only access (no breaking glass):**

**Rejected because:**

- ❌ Emergency scenarios: Data recovery, security incidents
- ❌ No legitimate use: Admin doesn't need daily access
- ❌ Still violates Need-to-Know principle

**C) Selected: Admin has NO access by default, breaking glass for emergencies:**

**Advantages:**

- ✅ **GDPR-compliant:** Need-to-Know principle
- ✅ **Separation of duties:** Clear role boundaries
- ✅ **Auditable:** Emergency access is logged
- ✅ **Flexible:** Can access in legitimate emergencies

**Access Matrix:**

| Resource               | Admin  | Super-Admin | HR  | Breaking Glass |
| ---------------------- | ------ | ----------- | --- | -------------- |
| System Configuration   | ✅     | ✅          | ❌  | -              |
| User Management        | ✅     | ✅          | ⚠️  | -              |
| Org Structure          | ✅     | ✅          | ✅  | -              |
| Work Instructions      | ✅     | ✅          | ✅  | -              |
| Employee Records       | ⚠️     | ⚠️          | ✅  | ✅             |
| **Employee Documents** | **❌** | **❌**      | ✅  | ✅             |
| **Salary Data**        | **❌** | **❌**      | ✅  | ✅             |
| Audit Logs             | ✅     | ✅          | ❌  | -              |
| Emergency Access Logs  | ❌     | ✅          | ❌  | -              |

⚠️ = Scope-dependent (via organizational scopes)

---

## Edge Cases & Security Considerations

### Edge Case 1: Nested Inheritance Blocks

**Scenario:**

```
Holding (no blocks)
└── Division (blocks: employee.read)
    └── Branch (blocks: employee_document.read)
```

**Question:** Does Branch block inherit from Division block?

**Decision:** **No automatic inheritance of blocks.**

**Rationale:**

- Branch explicitly controls its own blocks
- Division block applies only to Division
- Branch must explicitly set `applies_to_descendants: true` if it wants to protect its children

**Implementation:**

```php
public function blocksPermissionInheritance(string $permission): bool
{
    // Check this unit's blocks
    $blocks = $this->inheritance_blocks ?? [];
    $blockedPermissions = $blocks['blocked_permissions'] ?? [];

    if (in_array($permission, $blockedPermissions, true)) {
        return true;
    }

    // Check if ANY ancestor blocks (with applies_to_descendants)
    $ancestors = $this->ancestors()->get();
    foreach ($ancestors as $ancestor) {
        $ancestorBlocks = $ancestor->inheritance_blocks ?? [];
        $ancestorBlockedPerms = $ancestorBlocks['blocked_permissions'] ?? [];
        $appliesToDescendants = $ancestorBlocks['applies_to_descendants'] ?? false;

        if ($appliesToDescendants && in_array($permission, $ancestorBlockedPerms, true)) {
            return true;
        }
    }

    return false;
}
```

### Edge Case 2: Super-Admin Transfers to Child Org

**Scenario:**

```
1. User is super-admin on Holding
2. User transfers to Regional GmbH
3. User's Holding scope is removed
4. What happens to super-admin status?
```

**Decision:** **Super-admin flag is on the SCOPE, not the USER.**

**Implication:**

- Removing Holding scope → User loses super-admin status
- User in Regional GmbH = Regular admin (no super-admin possible)
- Must create new scope if user returns to Holding

**Rationale:**

- Super-admin is **contextual** (relative to organizational unit)
- Not a global user attribute
- Follows principle of least privilege

### Edge Case 3: Breaking Glass During Inheritance Block Change

**Scenario:**

```
1. Regional GmbH has no blocks (allows emergency access)
2. Super-admin requests emergency access (granted)
3. During active emergency access, Regional GmbH adds inheritance block
4. Does emergency access continue or get revoked?
```

**Decision:** **Active emergency access continues until expiration.**

**Rationale:**

- Emergency access is **time-bound** (max 4 hours)
- Revoking mid-access could disrupt critical operations
- Unit can monitor emergency access logs and investigate
- Unit can set `emergency_requires_approval: true` for future requests

**Implementation:**

```php
public function hasActiveEmergencyAccess(User $user, string $permission, ?OrganizationalUnit $unit): bool
{
    return EmergencyAccessLog::where('user_id', $user->id)
        ->where('permission', $permission)
        ->where(function ($q) use ($unit) {
            $q->whereNull('organizational_unit_id')
              ->orWhere('organizational_unit_id', $unit?->id);
        })
        ->where('access_granted_at', '<=', now())
        ->where('access_expires_at', '>', now())
        ->exists();

    // Note: Does NOT check current inheritance blocks
    // Active access is respected until expiration
}
```

### Edge Case 4: Multiple Root Units in Same Tenant

**Scenario:**

```
Tenant: "SecureGuard Services GmbH"
  ├── Holding A (root, parent_id = null)
  │   └── Branch A1
  └── Holding B (root, parent_id = null)
      └── Branch B1
```

**Question:** Can Holding A super-admin access Holding B data?

**Decision:** **No. Super-admin scope is specific to the root unit it's assigned to.**

**Rationale:**

- Multiple roots = Separate business entities (e.g., acquired companies)
- Super-admin on Root A ≠ Super-admin on Root B
- User needs separate scopes for each root

**Implementation:**

```php
public function hasAccessToUnit(OrganizationalUnit $unit, ?string $minimumLevel = null): bool
{
    $scopes = $this->organizationalScopes()->get();

    foreach ($scopes as $scope) {
        // Direct match
        if ($scope->organizational_unit_id === $unit->id) {
            return $this->checkAccessLevel($scope, $minimumLevel);
        }

        // Check descendants (with inheritance block check)
        if ($scope->include_descendants) {
            $isDescendant = OrganizationalUnitClosure::where('ancestor_id', $scope->organizational_unit_id)
                ->where('descendant_id', $unit->id)
                ->where('depth', '>', 0)
                ->exists();

            if ($isDescendant) {
                return $this->checkAccessLevel($scope, $minimumLevel);
            }
        }
    }

    return false;
    // Note: Does NOT check other root units (scope is explicit)
}
```

### Edge Case 5: Inheritance Block Wildcards

**Question:** Can blocks use wildcards (e.g., `employee.*`)?

**Decision:** **Yes, but with explicit validation.**

**Supported patterns:**

- `employee.*` → Blocks all employee permissions
- `employee_document.*` → Blocks all document permissions
- `*.read` → **NOT supported** (too broad, unclear semantics)

**Implementation:**

```php
public function blocksPermissionInheritance(string $permission): bool
{
    $blocks = $this->inheritance_blocks ?? [];
    $blockedPermissions = $blocks['blocked_permissions'] ?? [];

    foreach ($blockedPermissions as $blocked) {
        // Exact match
        if ($blocked === $permission) {
            return true;
        }

        // Wildcard match (only resource.*)
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

**Validation:**

```php
// In UpdateOrganizationalUnitRequest
'inheritance_blocks.blocked_permissions.*' => [
    'string',
    'regex:/^[a-z_]+(\.[a-z_*]+)?$/',  // resource.action or resource.*
    function ($attribute, $value, $fail) {
        // Reject *.action patterns
        if (str_starts_with($value, '*.')) {
            $fail('Wildcard patterns like *.action are not supported. Use resource.* instead.');
        }
    },
],
```

### Edge Case 6: Breaking Glass for Deleted Units

**Scenario:**

```
1. Super-admin requests emergency access to Unit X
2. During active access, Unit X is deleted
3. What happens?
```

**Decision:** **Emergency access log remains, but access is effectively revoked.**

**Rationale:**

- Unit deletion = Business decision (unit no longer exists)
- Data may be soft-deleted (still in database)
- Log preserves audit trail
- Policy check fails gracefully (unit not found → deny)

**Implementation:**

```php
Schema::table('emergency_access_logs', function (Blueprint $table) {
    $table->foreignUuid('organizational_unit_id')
        ->nullable()
        ->constrained('organizational_units')
        ->nullOnDelete();  // ← Set to NULL on unit deletion
});

// In policy
if ($unit === null) {
    // Unit was deleted during emergency access
    // Log error but allow emergency access to continue
    // (user may be recovering data from soft-deleted records)
    \Log::warning("Emergency access to deleted unit", [
        'user_id' => $user->id,
        'unit_id' => $unitId,
        'emergency_log_id' => $logId,
    ]);

    return false;  // Deny if unit truly gone
}
```

### Edge Case 7: Concurrent Emergency Access Requests

**Scenario:**

```
1. User requests emergency access to Unit X (2 hours)
2. Before expiration, user requests another emergency access to Unit X (1 hour)
3. What happens?
```

**Decision:** **Allow multiple concurrent emergency access grants.**

**Rationale:**

- Different resources may require separate justifications
- Shorter access for specific task (review document) vs. longer for investigation
- Audit trail shows all requests individually

**Implementation:**

```php
// Multiple active emergency access logs allowed
EmergencyAccessLog::create([
    'user_id' => $user->id,
    'organizational_unit_id' => $unit->id,
    'resource_type' => 'EmployeeDocument',
    'resource_id' => $document->id,
    'permission' => 'employee_document.read',
    'reason' => 'Review specific document for legal case',
    'urgency' => 'high',
    'access_granted_at' => now(),
    'access_expires_at' => now()->addHours(1),
]);

// Existing log for same unit still active:
EmergencyAccessLog::create([
    'user_id' => $user->id,
    'organizational_unit_id' => $unit->id,
    'resource_type' => 'Employee',
    'resource_id' => null,  // All employees
    'permission' => 'employee.read',
    'reason' => 'Security incident investigation',
    'urgency' => 'critical',
    'access_granted_at' => now()->subHour(1),
    'access_expires_at' => now()->addHours(3),
]);
```

### Security Consideration 1: Defense-in-Depth Layers

**Multiple validation layers prevent exploitation:**

1. **Request Validation Layer:** `StoreOrganizationalScopeRequest`

   - Validates target unit is root (if super-admin)
   - Checks permission formats
   - Validates inheritance block structure

2. **Policy Authorization Layer:** `OrganizationalUnitPolicy`

   - `manageScopes()`: Can user modify scopes for this unit?
   - `grantSuperAdmin()`: Can user grant super-admin for this unit?
   - Checks granter has root-unit super-admin scope

3. **Controller Layer:** `OrganizationalScopeController`

   - Double-checks authorization before creating scope
   - Validates super-admin flag separately
   - Logs scope creation

4. **Model Layer:** `UserInternalOrganizationalScope`

   - `canGrantSuperAdmin()`: Validates organizational hierarchy
   - `canRequestEmergencyAccessTo()`: Prevents upward escalation

5. **Database Layer:** Foreign key constraints
   - `user_id` → `users.id` (cascade delete)
   - `organizational_unit_id` → `organizational_units.id` (cascade delete)
   - Unique constraint: `(user_id, organizational_unit_id)`

**Why multiple layers?**

- **Single point of failure prevention:** If one layer has bug, others catch it
- **Fail-safe:** Default deny, explicit allow
- **Auditability:** Each layer logs its decision
- **Performance:** Early rejection (validation fails fast)

### Security Consideration 2: Audit Trail Requirements

**What must be logged?**

**1. Scope Creation/Modification:**

```php
// Log in scope_audit_logs table (to be created)
[
    'action' => 'scope_created',
    'user_id' => $granter->id,
    'target_user_id' => $scope->user_id,
    'organizational_unit_id' => $scope->organizational_unit_id,
    'access_level' => $scope->access_level,
    'is_super_admin' => $scope->is_super_admin,
    'include_descendants' => $scope->include_descendants,
    'reason' => $request->input('reason'),  // Should be required
    'timestamp' => now(),
]
```

**2. Inheritance Block Changes:**

```php
[
    'action' => 'inheritance_block_added',
    'organizational_unit_id' => $unit->id,
    'blocked_permissions' => ['employee.read', 'employee_document.read'],
    'reason' => $unit->inheritance_blocks['reason'],
    'modified_by' => $user->id,
    'timestamp' => now(),
]
```

**3. Emergency Access Requests:**

```php
[
    'action' => 'emergency_access_requested',
    'user_id' => $user->id,
    'organizational_unit_id' => $unit->id,
    'resource_type' => 'EmployeeDocument',
    'resource_id' => $document->id,
    'permission' => 'employee_document.read',
    'reason' => $request->input('reason'),
    'urgency' => 'critical',
    'duration_hours' => 2,
    'approved_by' => $approver->id ?? null,
    'timestamp' => now(),
]
```

**4. Emergency Access Usage:**

```php
[
    'action' => 'emergency_access_used',
    'emergency_log_id' => $log->id,
    'user_id' => $user->id,
    'resource_type' => 'EmployeeDocument',
    'resource_id' => $document->id,
    'accessed_fields' => ['name', 'contract_data', 'salary'],
    'ip_address' => $request->ip(),
    'user_agent' => $request->userAgent(),
    'timestamp' => now(),
]
```

**5. Privilege Escalation Attempts:**

```php
[
    'action' => 'privilege_escalation_blocked',
    'user_id' => $user->id,
    'attempted_action' => 'grant_super_admin',
    'target_unit_id' => $unit->id,
    'target_user_id' => $targetUser->id,
    'reason_blocked' => 'User does not have root-unit super-admin scope',
    'ip_address' => $request->ip(),
    'timestamp' => now(),
]
```

**Retention:**

- Emergency access logs: **7 years** (legal requirement)
- Scope modifications: **3 years** (compliance)
- Privilege escalation attempts: **Permanent** (security)

### Security Consideration 3: Attack Vectors & Mitigations

**Attack 1: Child-Org Admin Grants Super-Admin to Accomplice**

```php
// Attack attempt:
POST /organizational-units/{holdingId}/scopes
{
  "user_id": "accomplice-user-id",
  "access_level": "admin",
  "is_super_admin": true
}
```

**Mitigation:**

1. Request validation: Checks if organizational unit is root
2. Policy: `grantSuperAdmin()` verifies granter has root-unit super-admin scope
3. Controller: Double-checks authorization
4. Logs: Privilege escalation attempt is logged

**Result:** Request fails with 403 Forbidden

**Attack 2: Super-Admin Attempts Upward Escalation**

```php
// Scenario: Regional GmbH "super-admin" (shouldn't exist but assume bypass)
// Attempts breaking glass to Holding

POST /emergency-access
{
  "organizational_unit_id": "holding-id",  // Parent org
  "permission": "employee_document.read",
  "reason": "Data recovery"
}
```

**Mitigation:**

1. `canRequestEmergencyAccessTo()` checks if target is ancestor
2. Returns false if upward access detected
3. Logs privilege escalation attempt

**Result:** Request fails with 403 Forbidden

**Attack 3: Inheritance Block Removal by Unauthorized User**

```php
// Attack: Regional admin attempts to remove inheritance block set by parent

PATCH /organizational-units/{regionalGmbH-id}
{
  "inheritance_blocks": null
}
```

**Mitigation:**

1. Policy: `update()` checks user has 'write' or 'manage' access level
2. Special policy: `manageInheritanceBlocks()` requires 'admin' level
3. If block was set by parent org, requires parent-org admin to remove

**Result:** Request fails with 403 Forbidden

**Attack 4: SQL Injection in Inheritance Block Permissions**

```php
// Attack: Inject SQL via inheritance block

PATCH /organizational-units/{unit-id}
{
  "inheritance_blocks": {
    "blocked_permissions": [
      "employee.read'; DROP TABLE users; --"
    ]
  }
}
```

**Mitigation:**

1. Request validation: Regex pattern validation
2. JSON column: PostgreSQL safely handles JSON escaping
3. Permission checks: String comparison (no SQL execution)

**Result:** Validation fails, request rejected

---

## Implementation Plan

### Phase 1: Inheritance Blocking (Priority: High)

**Duration:** 2-3 weeks

**Tasks:**

1. Add `inheritance_blocks` JSONB column to `organizational_units` table
2. Update `OrganizationalUnit` model with blocking methods
3. Modify `hasAccessToUnit()` to check inheritance blocks
4. Update all policies (Employee, EmployeeDocument, etc.) with block checks
5. Create API endpoints for managing inheritance blocks
6. Write comprehensive tests (unit, integration, E2E)
7. Update documentation

**Database Migration:**

```php
Schema::table('organizational_units', function (Blueprint $table) {
    $table->jsonb('inheritance_blocks')->nullable();
    $table->index('inheritance_blocks');  // GIN index for JSONB queries
});
```

**Testing Checklist:**

- [ ] Unit blocks permission inheritance correctly
- [ ] Wildcard patterns work (`employee.*`)
- [ ] `applies_to_descendants` flag works
- [ ] Direct scope overrides block
- [ ] Multiple blocks on different units work together
- [ ] Performance: N+1 query prevention
- [ ] Edge cases: Deleted units, null values

### Phase 2: Super-Admin Restrictions (Priority: High)

**Duration:** 2 weeks

**Tasks:**

1. Add `is_super_admin` boolean column to `user_internal_organizational_scopes`
2. Create `grantSuperAdmin()` policy method
3. Update request validation for super-admin checks
4. Modify controller to enforce super-admin rules
5. Add `canRequestEmergencyAccessTo()` method
6. Write comprehensive tests
7. Update documentation

**Database Migration:**

```php
Schema::table('user_internal_organizational_scopes', function (Blueprint $table) {
    $table->boolean('is_super_admin')->default(false);
    $table->index(['is_super_admin', 'user_id']);
});
```

**Testing Checklist:**

- [ ] Super-admin can only be granted for root units
- [ ] Only root-unit super-admins can grant super-admin
- [ ] Child-org admin cannot grant super-admin
- [ ] Child-org "super-admin" cannot access parent org
- [ ] Privilege escalation attempts are blocked and logged
- [ ] Super-admin flag is removed when scope is deleted

### Phase 3: Breaking Glass Emergency Access (Priority: Medium)

**Duration:** 3-4 weeks

**Tasks:**

1. Create `emergency_access_logs` table
2. Create emergency access request API
3. Implement time-limited token generation
4. Update policies to check emergency access first
5. Add automatic expiration (scheduled job)
6. Implement notification system (email, Slack)
7. Optional: Approval workflow (4-eyes principle)
8. Create emergency access audit dashboard
9. Write comprehensive tests
10. Update documentation

**Database Migration:**

```php
Schema::create('emergency_access_logs', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->foreignUuid('user_id')->constrained()->cascadeOnDelete();
    $table->foreignUuid('tenant_id')->constrained('tenant_keys')->cascadeOnDelete();
    $table->foreignUuid('organizational_unit_id')->nullable()
        ->constrained('organizational_units')->nullOnDelete();

    $table->string('resource_type');
    $table->uuid('resource_id')->nullable();
    $table->string('action');
    $table->string('permission');

    $table->text('reason');
    $table->enum('urgency', ['low', 'medium', 'high', 'critical']);
    $table->timestamp('access_granted_at');
    $table->timestamp('access_expires_at');

    $table->foreignUuid('approved_by')->nullable()->constrained('users');
    $table->timestamp('approved_at')->nullable();

    $table->json('accessed_fields')->nullable();
    $table->integer('access_count')->default(0);
    $table->timestamp('last_accessed_at')->nullable();
    $table->ipAddress('ip_address')->nullable();

    $table->timestamps();

    $table->index(['user_id', 'created_at']);
    $table->index(['organizational_unit_id', 'created_at']);
    $table->index(['access_expires_at']);
});
```

**Testing Checklist:**

- [ ] Emergency access request creates log entry
- [ ] Access expires automatically after time limit
- [ ] Policy checks emergency access before normal checks
- [ ] All emergency access is logged (what fields accessed)
- [ ] Notifications sent to DPO when emergency access used
- [ ] Cannot request emergency access upward
- [ ] Approval workflow works (if enabled)
- [ ] Dashboard shows emergency access history

### Phase 4: Audit & Compliance Features (Priority: Medium)

**Duration:** 1-2 weeks

**Tasks:**

1. Create audit dashboard for inheritance blocks
2. Create audit dashboard for emergency access
3. Add reports: "Who has access to what?"
4. Add reports: "All emergency access in last 30 days"
5. Add alerts: "Unusual emergency access pattern detected"
6. GDPR compliance report: Data access audit trail
7. Update documentation with compliance procedures

**Testing Checklist:**

- [ ] Dashboard shows all inheritance blocks
- [ ] Dashboard shows all emergency access
- [ ] Reports are accurate and performant
- [ ] Alerts trigger correctly
- [ ] Export functionality works (CSV, PDF)

---

## Consequences

### Positive Consequences

**1. GDPR Compliance:**

- ✅ Need-to-Know principle enforced at organizational level
- ✅ Data minimization through inheritance blocking
- ✅ Complete audit trail for emergency access
- ✅ Technical measures demonstrate due diligence

**2. Security Improvements:**

- ✅ Prevents privilege escalation (horizontal and upward)
- ✅ Defense-in-depth through multiple validation layers
- ✅ Super-admin restricted to highest privilege level
- ✅ Emergency access is time-limited and audited

**3. Organizational Autonomy:**

- ✅ Subsidiaries can protect their data independently
- ✅ Clear security boundaries between legal entities
- ✅ Self-documenting security policies (inheritance blocks)

**4. Operational Flexibility:**

- ✅ One scope with inheritance vs. multiple scopes without
- ✅ Breaking glass enables emergency operations
- ✅ Resource-specific blocking (work instructions vs. employee data)

**5. Auditability:**

- ✅ Complete trail of scope assignments
- ✅ Complete trail of inheritance block changes
- ✅ Complete trail of emergency access usage
- ✅ Forensic analysis possible for security incidents

### Negative Consequences

**1. Complexity:**

- ⚠️ Additional concept: inheritance blocking (learning curve)
- ⚠️ More configuration: blocks must be set correctly
- ⚠️ Query complexity: Check blocks on every permission check

**Mitigation:**

- Good documentation with examples
- UI helpers for common scenarios
- Default templates for subsidiaries

**2. Performance:**

- ⚠️ Additional query: Check inheritance blocks
- ⚠️ JSON field queries (may be slower)

**Mitigation:**

- GIN indexes on JSONB columns
- Caching of inheritance blocks
- Eager loading in queries

**3. Migration Effort:**

- ⚠️ Existing scopes must be reviewed
- ⚠️ Subsidiaries must configure blocks
- ⚠️ Training required for administrators

**Mitigation:**

- Migration scripts with sensible defaults
- Step-by-step migration guide
- Training materials and videos

**4. Breaking Changes:**

- ⚠️ Existing super-admins on child orgs become invalid
- ⚠️ Admin role loses default access to employee documents

**Mitigation:**

- Clear communication of changes
- Migration period with warnings
- Automatic scope adjustments where possible

### Risks

**Risk 1: Misconfigured Inheritance Blocks**

**Description:** Admin accidentally blocks critical permissions, breaking workflows.

**Probability:** Medium
**Impact:** Medium (operational disruption)

**Mitigation:**

- Validation: Cannot block permissions not in system
- Warnings: "This will affect N users"
- Preview: "Show who will lose access"
- Rollback: Track change history, allow undo

**Risk 2: Emergency Access Abuse**

**Description:** Super-admin uses breaking glass for non-legitimate purposes.

**Probability:** Low
**Impact:** High (data breach, GDPR violation)

**Mitigation:**

- Mandatory justification field
- Email notifications to DPO
- Regular audit reviews
- Disciplinary procedures for abuse

**Risk 3: Performance Degradation**

**Description:** Inheritance block checks slow down permission checks.

**Probability:** Low
**Impact:** Medium (slow response times)

**Mitigation:**

- Caching: Store blocks in Redis
- Indexing: GIN indexes on JSONB
- Query optimization: Eager loading
- Benchmarking: Test with large datasets

**Risk 4: Privilege Escalation via Bug**

**Description:** Bug in validation allows bypassing super-admin restrictions.

**Probability:** Low
**Impact:** Critical (security breach)

**Mitigation:**

- Multiple validation layers (defense-in-depth)
- Comprehensive test suite (>95% coverage)
- Security audits
- Penetration testing
- Bug bounty program

---

## Related ADRs

**Note:** This section will be populated after checking existing ADRs to avoid duplicating information before it's fully documented.

Potential relationships:

- ADR-007: Organizational Structure Hierarchy (extends with blocking)
- ADR-005: RBAC Design Decisions (super-admin concept)
- ADR-008: User-Based Tenant Resolution (tenant isolation)

---

## References

### Legal & Compliance

- **GDPR Article 5(1)(c):** Data minimization principle
- **GDPR Article 32:** Security of processing
- **GDPR Article 5(2):** Accountability principle
- **BetrVG §99:** Works council co-determination rights
- **ISO/IEC 27001:2013:** Access control (A.9.1.1, A.9.1.2)

### Technical Standards

- **OWASP Top 10 2021:** A01:2021 – Broken Access Control
- **NIST SP 800-53:** AC-2 (Account Management), AC-6 (Least Privilege)
- **CIS Controls v8:** Control 3 (Data Protection), Control 6 (Access Control)

### Industry Best Practices

- **Principle of Least Privilege:** Grant minimum necessary access
- **Separation of Duties:** Admin ≠ HR
- **Defense-in-Depth:** Multiple security layers
- **Breaking Glass Principle:** Emergency access with accountability
- **Need-to-Know Principle:** Access only when required

### Internal Documentation

- **TDD Principles:** Test-driven development for security features
- **ADR Template:** SecPal architectural decision record format
- **Security Guidelines:** Secure coding practices

---

## Open Questions

**Question 1:** Should inheritance blocks support temporal rules?

**Example:**

```json
{
  "blocked_permissions": ["employee.read"],
  "effective_from": "2025-01-01",
  "effective_until": "2025-12-31",
  "reason": "Temporary isolation during legal restructuring"
}
```

**Pros:**

- Useful for temporary isolation (e.g., during acquisition)
- Automatic re-enabling after period

**Cons:**

- Additional complexity
- Could be achieved with manual changes

**Decision:** Defer to Phase 5. Not critical for initial implementation.

---

**Question 2:** Should emergency access require 4-eyes approval by default?

**Pros:**

- Stronger security (no single person can break glass alone)
- Better audit trail (approval documented)

**Cons:**

- Delays emergency response (approver must be available)
- May not be necessary for all organizations

**Decision:** Make it **configurable per organizational unit**:

```json
{
  "inheritance_blocks": {
    "emergency_requires_approval": true,
    "emergency_approvers": ["dpo@company.com", "legal@company.com"]
  }
}
```

---

**Question 3:** Should we support "read-only super-admin"?

**Use case:** Compliance officer needs to audit all data but not modify.

**Pros:**

- Lower risk than full super-admin
- Useful for external auditors

**Cons:**

- Additional complexity
- Can be achieved with read-only permissions + breaking glass

**Decision:** Defer to Phase 5. Use regular scopes with read-only permissions for now.

---

**Question 4:** Should inheritance blocks be versioned?

**Use case:** Track changes to blocks over time, show who added/removed blocks when.

**Pros:**

- Full audit trail of block changes
- Can answer "When did we start blocking employee.read?"

**Cons:**

- Additional database table
- Complexity in UI (show history)

**Decision:** Implement in Phase 4 (Audit & Compliance). Use Laravel's model events to track changes.

---

## Approval

**Author:** GitHub Copilot (AI Assistant)
**Date:** 2025-12-20

**Review Required By:**

- [ ] Security Team Lead
- [ ] Data Protection Officer (DPO)
- [ ] CTO / Technical Architect
- [ ] Legal Counsel (GDPR compliance)

**Approval Status:** Pending Review

---

## Changelog

- **2025-12-20:** Initial draft created
- **2025-12-20:** Added edge cases and security considerations
- **2025-12-20:** Added implementation plan and testing checklists
