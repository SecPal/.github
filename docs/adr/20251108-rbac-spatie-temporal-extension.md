<!--
SPDX-FileCopyrightText: 2024 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-004: RBAC System with Spatie Laravel-Permission and Temporal Extensions

**Status:** Accepted

**Date:** 2024-11-08

**Deciders:** @kevalyq

## Context

SecPal requires a comprehensive Role-Based Access Control (RBAC) system with specific requirements:

### Business Requirements

- **Variable roles**: Not hardcoded - each on-premise installation must support custom role definitions
- **UI-manageable**: Roles and permissions should be configurable through administrative interface
- **Temporal assignments**: Roles must support time-limited access with automatic expiration
- **Audit trail**: All role assignments and revocations must be logged for compliance

### Primary Use Cases

1. **Works Council Access**: Grant temporary access to employee personnel files during hiring approval process
2. **Vacation Coverage**: Temporarily assign manager permissions during absence
3. **Event-Based Elevation**: Temporary elevated permissions for specific events or projects
4. **Compliance**: Enforce principle of least privilege through automatic role expiration

### Technical Requirements

- Roles stored in database (not hardcoded enums)
- Support for `valid_from` and `valid_until` timestamps
- Automatic revocation of expired roles
- Scoped permissions (branch, location, division)
- Integration with Laravel policies
- No pre-expiry notifications required (simplified workflow)

## Decision

Implement a **hybrid approach** combining Spatie Laravel-Permission as the foundation with custom temporal role extensions:

### Architecture

```
┌─────────────────────────────────────────────────┐
│ Spatie Laravel-Permission (Base Layer)         │
│ - Role management (database-driven)             │
│ - Permission system                             │
│ - Policy integration                            │
│ - Multi-tenancy support                         │
└─────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ Custom Temporal Extensions                      │
│ - Extended pivot table (model_has_roles)        │
│ - Temporal columns (valid_from, valid_until)    │
│ - Active role scope filtering                   │
│ - Auto-expire scheduled command                 │
│ - Audit trail logging                           │
└─────────────────────────────────────────────────┘
```

### Implementation Components

**1. Spatie Base (Provided)**

- `roles` table: Database-driven role definitions
- `permissions` table: Granular permission management
- `model_has_roles` pivot: User-role assignments
- `role_has_permissions` pivot: Role-permission mappings
- Policy integration helpers

**2. Custom Extensions (Our Implementation)**

Extended pivot table schema:

```php
model_has_roles:
  // Spatie columns
  - model_type, model_id, role_id, team_id

  // Our temporal extensions
  + valid_from (timestamp nullable)     // Role becomes active
  + valid_until (timestamp nullable)    // Role expires
  + auto_revoke (boolean default true)  // Auto-delete on expiry
  + assigned_by (uuid nullable)         // Who assigned the role
  + reason (text nullable)              // Assignment justification
  + created_at, updated_at
```

**3. Scheduled Task**

```php
// Console/Commands/ExpireRoles.php
// Runs every minute via Laravel scheduler
- Find roles where valid_until < now()
- Log to audit trail
- Delete expired assignments
```

**4. Eloquent Scope**

```php
// Only consider currently valid roles
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

## Alternatives Considered

### Option A: Complete Custom Implementation

**Description:** Build RBAC system from scratch without external dependencies.

**Pros:**

- Full control over all features including temporal logic
- No external dependency risks
- Perfectly tailored to SecPal requirements

**Cons:**

- ❌ Significant development time (8-10 days)
- ❌ Must maintain security updates ourselves
- ❌ Reinventing well-solved problems
- ❌ No community support or battle-testing
- ❌ UI management requires building from scratch

**Verdict:** Rejected - Too much effort for basic RBAC functionality that Spatie provides reliably.

### Option B: Spatie Only (No Temporal Features)

**Description:** Use Spatie as-is without temporal extensions.

**Pros:**

- Zero custom code
- Fastest implementation
- Maximum community support

**Cons:**

- ❌ Cannot support time-limited role assignments
- ❌ Works Council use case not feasible
- ❌ Vacation coverage requires manual revocation
- ❌ No automatic expiration for compliance

**Verdict:** Rejected - Temporal roles are a core requirement.

### Option C: Spatie + Temporal Extension ✅ CHOSEN

**Description:** Use Spatie as foundation, extend pivot table for temporal features.

**Pros:**

- ✅ Battle-tested permission system (100k+ installations)
- ✅ Database-driven roles (UI-friendly)
- ✅ Community support and security updates
- ✅ Fast implementation (5-6 days vs 10)
- ✅ Full control over temporal logic
- ✅ Existing Filament/Nova plugins for role management UI

**Cons:**

- ⚠️ External dependency (acceptable risk - widely used)
- ⚠️ Must test Spatie upgrades for compatibility
- ⚠️ Temporal logic maintenance is our responsibility

**Verdict:** Accepted - Best balance of proven foundation and custom features.

## Consequences

### Positive

- **Faster Development**: 5-6 days instead of 10+ days for custom solution
- **Proven Foundation**: Spatie has 100k+ monthly downloads and years of production use
- **UI-Ready**: Filament Spatie plugin provides ready-made role management interface
- **Variable Roles**: Database-driven roles support per-installation customization out of the box
- **Community Support**: Security updates, bug fixes, and best practices from Laravel community
- **Well-Documented**: Extensive documentation and examples available
- **Policy Integration**: Seamless integration with Laravel's authorization system

### Negative

- **External Dependency**: Reliance on third-party package (mitigated by its popularity and stability)
- **Upgrade Testing**: Must verify temporal extensions remain compatible with Spatie updates
- **Temporal Maintenance**: Custom temporal logic must be maintained by our team

### Neutral

- **Learning Curve**: Team must learn Spatie API (well-documented, widely used)
- **Pivot Table Customization**: Requires extending Spatie's pivot model (standard Laravel practice)

## Implementation Plan

### Phase 1: Foundation (Day 1-2)

- Install Spatie Laravel-Permission package
- Publish and run base migrations
- Extend `model_has_roles` pivot table with temporal columns
- Create custom pivot model `TemporalRoleUser`
- Override `User::roles()` relationship to use custom pivot

### Phase 2: Temporal Logic (Day 3)

- Implement `active()` eloquent scope for temporal filtering
- Create scheduled command `roles:expire` (runs every minute)
- Build audit trail table and model (`role_assignments_log`)
- Write unit tests for temporal filtering and expiration

### Phase 3: API & Integration (Day 4-5)

- API endpoints for role assignment with temporal parameters
- Policy classes (e.g., `EmployeePolicy`)
- Middleware integration on routes
- Feature tests for API endpoints
- Integration tests for policy enforcement

### Phase 4: Documentation (Day 6)

- API documentation updates
- Developer guide for temporal roles
- Update README with RBAC section

## Related

- **Issue:** #5 (Implement RBAC System)
- **Blocks:** #68 (Employee Management), #69 (Works Council), #70 (Shift Planning), #102 (Work Instructions)
- **Spatie Package:** [spatie/laravel-permission](https://github.com/spatie/laravel-permission)
- **Documentation:** [Spatie Docs](https://spatie.be/docs/laravel-permission)

## References

- Spatie Laravel-Permission: <https://github.com/spatie/laravel-permission>
- Laravel Authorization: <https://laravel.com/docs/12.x/authorization>
- Temporal Role Patterns: Martin Fowler's "Temporal Patterns" (enterprise patterns)
- GDPR Access Control Requirements: <https://gdpr-info.eu/art-32-gdpr/>
