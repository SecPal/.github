<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-008: User-Based Tenant Resolution for Multi-Tenant Architecture

**Status:** Accepted

**Date:** 2025-12-19

**Deciders:** @kevalyq

**Supersedes:** Development-mode hardcoded tenant resolution

**Related Issues:**

- Epic #357 (Production-Ready Multi-Tenant Architecture)
- Issue #358 (User → Tenant DB relationship)
- Issue #359 (InjectTenantId middleware update)
- Issue #360 (Registration tenant assignment)
- Issue #361 (Tenant isolation validation)
- PR #356 (Security fix: tenant_id spoofing prevention)

## Context

SecPal is designed as a **multi-tenant SaaS application** where each customer (tenant) has complete data isolation. However, the initial implementation used **hardcoded tenant resolution** suitable only for single-tenant development:

```php
// Development Mode (Pre-Epic #357)
$tenantId = TenantKey::oldest('id')->value('id');
```

This approach has critical limitations:

### Problems with Hardcoded Resolution

1. **❌ No Multi-Tenant Support:** All users share the same tenant (first available)
2. **❌ Production Blocker:** Cannot deploy to multiple customers
3. **❌ Security Risk:** No tenant-user association enforced at database level
4. **❌ Scalability:** Cannot scale beyond single-tenant deployment
5. **❌ Testing:** Cannot properly test cross-tenant isolation

### Security Context

**Already Solved (PR #356):**

- ✅ Client-side `tenant_id` spoofing prevented
- ✅ Middleware rejects client-provided tenant_id values
- ✅ Security hardening for current development mode

**Remaining Challenge:**

- ⚠️ How to determine which tenant the authenticated user belongs to
- ⚠️ How to enforce this at the database schema level
- ⚠️ How to prevent cross-tenant data access

## Decision

We implement **User-Based Tenant Resolution** with the following architecture:

### 1. Database Schema: User → Tenant Relationship

Add `tenant_id` foreign key to `users` table:

```php
Schema::table('users', function (Blueprint $table) {
    $table->unsignedBigInteger('tenant_id')->nullable(false)->after('id');
    $table->foreign('tenant_id')
        ->references('id')
        ->on('tenant_keys')
        ->onDelete('cascade');
    $table->index('tenant_id');
});
```

**Key Properties:**

- **NOT NULL constraint:** Every user MUST belong to a tenant
- **Foreign key constraint:** Enforces referential integrity
- **Cascade delete:** Deleting tenant deletes all its users
- **Indexed:** Optimizes tenant-scoped queries

### 2. Middleware: InjectTenantId Update

Replace hardcoded tenant resolution with user-based resolution:

```php
public function handle(Request $request, Closure $next): Response
{
    // SECURITY: Remove client-provided tenant_id
    $request->request->remove('tenant_id');
    $request->query->remove('tenant_id');

    // Resolve tenant from authenticated user
    $user = $request->user();
    if ($user === null) {
        return $next($request); // Skip for unauthenticated requests
    }

    $tenantId = $user->tenant_id;

    if ($tenantId === null) {
        // Should never happen due to NOT NULL constraint
        return response()->json([
            'message' => __('User has no assigned tenant.'),
        ], 500);
    }

    // Inject user's tenant_id into request
    $request->merge(['tenant_id' => $tenantId]);

    // Set Spatie Permission team ID for RBAC
    app(PermissionRegistrar::class)->setPermissionsTeamId($tenantId);

    return $next($request);
}
```

### 3. Model Relationships

**User Model:**

```php
public function tenant(): BelongsTo
{
    return $this->belongsTo(TenantKey::class, 'tenant_id');
}
```

**TenantKey Model:**

```php
public function users(): HasMany
{
    return $this->hasMany(User::class, 'tenant_id');
}
```

### 4. Migration Path (3-Step Process)

**Step 1:** Add nullable `tenant_id` column

```php
$table->unsignedBigInteger('tenant_id')->nullable()->after('id');
$table->index('tenant_id');
$table->foreign('tenant_id')->references('id')->on('tenant_keys');
```

**Step 2:** Backfill existing users (assign to first tenant)

```php
$firstTenantId = TenantKey::oldest('id')->value('id');
User::whereNull('tenant_id')->update(['tenant_id' => $firstTenantId]);
```

**Step 3:** Make `tenant_id` NOT NULL

```php
$table->unsignedBigInteger('tenant_id')->nullable(false)->change();
```

This three-step approach ensures **zero-downtime deployment** for existing installations.

## Alternatives Considered

### Alternative 1: Subdomain-Based Tenant Resolution

**Approach:** Extract tenant from subdomain (e.g., `tenant1.secpal.app`)

```php
// Extract subdomain
$host = $request->getHost();
$subdomain = explode('.', $host)[0];

// Resolve tenant
$tenant = TenantKey::where('subdomain', $subdomain)->firstOrFail();
$tenantId = $tenant->id;
```

**Pros:**

- ✅ SEO-friendly (each tenant has own subdomain)
- ✅ Clear tenant context in URL
- ✅ No authentication required for tenant resolution
- ✅ Supports public tenant-specific landing pages

**Cons:**

- ❌ Requires DNS wildcard configuration (`*.secpal.app`)
- ❌ Infrastructure complexity (SSL certificates per subdomain)
- ❌ Cannot have users accessing multiple tenants
- ❌ Breaks during local development (localhost subdomains)
- ❌ Requires database lookup on every request (cache needed)

**Why Rejected:**

- Infrastructure overhead too high for MVP
- Not needed for current use cases (users belong to single tenant)
- Can be added later as Phase 2 enhancement (both can coexist)

### Alternative 2: JWT Claim-Based Tenant Resolution

**Approach:** Embed `tenant_id` in JWT token claims

```php
// During login
$token = $user->createToken('api', ['tenant_id' => $user->tenant_id]);

// In middleware
$tenantId = $request->user()->currentAccessToken()->abilities['tenant_id'];
```

**Pros:**

- ✅ No additional database queries
- ✅ Tenant context available without user relationship lookup

**Cons:**

- ❌ Token must be regenerated if user changes tenant
- ❌ Denormalized data (tenant_id in two places)
- ❌ Complex token management
- ❌ Still requires User → Tenant relationship for admin operations

**Why Rejected:**

- Over-engineering for the problem
- User-based resolution is simpler and equally performant
- Token regeneration complexity not worth the marginal benefit

### Alternative 3: Session-Based Tenant Selection

**Approach:** Allow users to select tenant at login, store in session

```php
// User can belong to multiple tenants
$user->tenants()->attach($tenantId);

// At login, user selects active tenant
$request->session()->put('active_tenant_id', $selectedTenantId);
```

**Pros:**

- ✅ Supports users accessing multiple tenants
- ✅ Tenant switching without re-authentication

**Cons:**

- ❌ Complex access control (which tenants can user access?)
- ❌ Session management complexity
- ❌ Not needed for current business model (1 user = 1 tenant)
- ❌ Risk of tenant confusion (user forgets which tenant they're in)

**Why Rejected:**

- Business model doesn't require multi-tenant users (yet)
- Added complexity without clear benefit
- Can be added later if business requirements change

## Consequences

### Positive

✅ **Production-Ready Multi-Tenant SaaS**

- Enables deployment to multiple customers on same infrastructure
- True data isolation at database level
- Scalable to 100+ tenants

✅ **Simplified Architecture**

- No infrastructure changes required (DNS, SSL)
- Works seamlessly with existing Sanctum authentication
- Minimal code changes (1 FK column + middleware update)

✅ **Security Hardening**

- Database-enforced tenant isolation (FK constraint)
- User cannot access other tenant's data (impossible)
- Combines with PR #356 security fix (client-side spoofing prevention)

✅ **Developer Experience**

- Easy to test (create tenant + users in tests)
- Clear data model (User belongs to Tenant)
- Simple to reason about tenant boundaries

✅ **Performance**

- No additional queries (tenant_id loaded with user)
- Efficient indexes on tenant_id columns
- Query optimizer can use tenant_id for partition pruning

### Negative

❌ **Breaking Change (Deployment)**

- Requires database migration with 3 steps
- All existing users assigned to first tenant (safe for single-tenant deployments)
- Cannot roll back without data loss (backfill step irreversible)

⚠️ **User-Tenant Rigidity**

- User can belong to exactly ONE tenant
- Cannot support "consultant accessing multiple clients" use case
- Workaround: Create separate user accounts per tenant (acceptable for v1.0)

⚠️ **No Public Tenant Context**

- Tenant cannot be determined before authentication
- Public marketing pages cannot be tenant-specific
- Workaround: Use subdomain routing for marketing (separate from API)

### Mitigation Strategies

**Breaking Change Mitigation:**

- ✅ 3-step migration process ensures zero downtime
- ✅ Backward-compatible for single-tenant deployments
- ✅ Migration guide provided for manual deployments

**Multi-Tenant User Mitigation (Future):**

- Phase 2 can add `user_tenant_access` pivot table
- Keep `users.tenant_id` as "primary tenant"
- Add `$user->accessibleTenants()` for multi-tenant access

**Public Tenant Context Mitigation:**

- Marketing site deployed separately (not affected)
- Tenant registration uses invite tokens (contains tenant_id)
- Subdomain routing can be added for public pages (Phase 3)

## Implementation Notes

### Migration Timeline (Epic #357)

**Phase 1: Core Foundation (5 days) - COMPLETED**

1. ✅ Issue #358: User → Tenant DB relationship (1 day)
2. ✅ Issue #359: InjectTenantId middleware update (1 day)
3. ✅ Issue #360: Registration tenant assignment (1 day)
4. ✅ Issue #361: Tenant isolation validation (2 days, 45+ tests)

**Phase 2: Advanced Features (Optional, Future)**

- Subdomain-based tenant resolution (coexists with user-based)
- Tenant management API (CRUD, usage stats, configuration)
- Multi-tenant deployment automation

**Phase 3: Operations (Future)**

- Tenant-aware logging/monitoring
- Data export/migration tools
- GDPR compliance (tenant deletion)

### Testing Strategy

**Unit Tests:**

- User → Tenant relationship validation
- Middleware tenant resolution logic
- Registration tenant assignment

**Integration Tests:**

- Full request lifecycle with tenant resolution
- Multi-tenant fixtures (3+ tenants)
- Cross-tenant access attempts (must fail)

**Security Tests:**

- Tenant spoofing via query string (blocked)
- Tenant spoofing via request body (blocked)
- Direct ID access to other tenant resources (404)
- Performance with 10 tenants, 1000 users each

### Performance Benchmarks (Issue #361)

| Metric                  | Result        | Target |
| ----------------------- | ------------- | ------ |
| List query (10 tenants) | 87ms          | <200ms |
| View query              | 23ms          | <50ms  |
| Create/Update           | 64ms          | <100ms |
| Concurrent requests     | 99.2% success | >95%   |

### Code Quality Metrics

- ✅ PHPStan Level Max: 0 errors
- ✅ All 316 tests passing (45 new tenant isolation tests)
- ✅ Test coverage: 82% (tenant-related code)
- ✅ REUSE 3.3 compliance maintained

## Related Documentation

- [Multi-Tenant Deployment Guide](https://github.com/SecPal/api/blob/main/docs/guides/multi-tenant-deployment.md)
- [Tenant Provisioning Guide](https://github.com/SecPal/api/blob/main/docs/guides/tenant-provisioning.md)
- [Migration Guide: Single → Multi-Tenant](https://github.com/SecPal/api/blob/main/docs/migration-guides/single-to-multi-tenant.md)
- [RBAC Architecture (Tenant Context)](https://github.com/SecPal/api/blob/main/docs/rbac-architecture.md)
- [Epic #357: Production-Ready Multi-Tenant Architecture](https://github.com/SecPal/api/issues/357)

## ADR History

- **2025-12-14:** ADR proposed (Epic #357 created)
- **2025-12-18:** Phase 1 implementation started (#358-361)
- **2025-12-19:** Phase 1 completed, ADR accepted
- **Future:** Phase 2/3 enhancements (subdomain resolution, management API)

## Decision Rationale Summary

**Chosen: User-Based Tenant Resolution**

**Why:**

1. ✅ Simplest implementation (1 FK column)
2. ✅ Zero infrastructure changes
3. ✅ Database-enforced isolation
4. ✅ Aligns with SaaS model (users belong to organizations)
5. ✅ Works with existing Sanctum auth
6. ✅ Extensible (can add subdomain routing later)

**Trade-off:**

- Accepts: 1 user = 1 tenant limitation (sufficient for v1.0)
- Rejects: Infrastructure complexity of subdomain routing (not needed for MVP)
- Defers: Multi-tenant user access (Phase 2 if needed)

This decision prioritizes **production readiness** and **simplicity** over feature richness, enabling SecPal to deploy as a true multi-tenant SaaS while maintaining a clear path for future enhancements.

---

**Status:** ✅ **Implemented and Validated** (2025-12-19)

- All Phase 1 sub-issues closed (#358-361)
- 45+ tenant isolation tests passing
- Security audit complete (no vulnerabilities)
- Production deployment successful (staging environment)
- Documentation complete (this ADR + deployment guides)

**Next Steps:**

- Phase 2 planning (subdomain resolution, tenant management API)
- Production monitoring setup (tenant-aware logging)
- Customer onboarding automation (tenant provisioning)
