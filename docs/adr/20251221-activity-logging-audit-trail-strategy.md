<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-010: Activity Logging & Audit Trail Strategy

## Status

**Proposed** (Draft - awaiting review)

## Date

2025-12-21

## Context

### The Problem: Comprehensive Audit Trail for GDPR & Legal Compliance

SecPal requires a **legally compliant, tamper-proof audit trail** for all user activities, system changes, and data access events. This audit trail must satisfy multiple legal and regulatory requirements while remaining performant and maintainable.

#### Legal Requirements

**GDPR Article 30 - Records of Processing Activities:**

> The controller shall maintain records of processing activities, including [...] a description of the technical and organisational security measures.

**GDPR Article 32 - Security of Processing:**

> The ability to ensure ongoing confidentiality, integrity, availability and resilience of processing systems and services.

**German BewachV §21 - Buchführung und Aufbewahrung:**

> Die Aufzeichnungen und Belege sind bis zum Schluss des dritten auf den Zeitpunkt ihrer Entstehung folgenden Kalenderjahres in den Geschäftsräumen aufzubewahren.

**Example:** Log created 15.03.2025 → retention until 31.12.2028 (not just 3 years, but until end of the 3rd following calendar year)

**BetrVG (Works Council Rights):**

> Betriebsrat has co-determination rights for personal data processing - all access must be logged.

#### Business Requirements

1. **Comprehensive Logging:**
   - All CRUD operations on critical data (employees, contracts, salaries)
   - Authentication events (login, logout, failed attempts)
   - Permission changes (role assignments, scope modifications)
   - Emergency access (breaking glass, ADR-009)
   - Data exports and reports

2. **Organizational Scope Isolation:**
   - Regional subsidiaries see only their logs
   - Parent organizations cannot access blocked subsidiary logs
   - Respects inheritance blocking (ADR-009)

3. **Tamper-Proof Evidence:**
   - Detect any modification or deletion of log entries
   - Cryptographically verifiable integrity
   - Legally admissible in court proceedings

4. **Performance:**
   - Logging must not impact application performance
   - Fast queries for audit dashboards
   - Efficient storage for millions of logs

5. **GDPR Retention:**
   - Automatic deletion after retention period
   - Maintain integrity even after deletion
   - Balance between compliance and data minimization

### Current Situation

- **✅ Exists:** `RoleAssignmentLog` (immutable RBAC audit trail)
- **✅ Planned:** OpenTimestamp integration (ADR-002, Guard Book Events)
- **❌ Missing:** General activity logging for all user actions
- **❌ Missing:** Scoped access control for logs
- **❌ Missing:** Tamper-proof chaining mechanism
- **❌ Missing:** Automated retention policy enforcement

---

## Decision

We will implement a **3-Tier Hybrid Logging Architecture** using:

1. **Spatie Laravel Activity Log** as foundation (battle-tested, mature)
2. **Custom extensions** for scoping, integrity, and retention
3. **Hash Chain + Merkle Tree + OpenTimestamp** for tamper-proof evidence

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Standard Activity Logs (1 year retention)          │
│ - CRUD operations (non-sensitive)                           │
│ - Hash Chain for tamper detection                           │
│ - Soft delete → hard delete after 2 years                   │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 2: Security-Critical Logs (3 years retention)         │
│ - Authentication, RBAC changes, scope modifications        │
│ - Hash Chain + Merkle Tree (hourly batching)               │
│ - Archive (hash only) after 3 years → delete after 5 years │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Tier 3: Legal-Critical Logs (7-10 years retention)         │
│ - HR access, breaking glass, contracts, guard book events  │
│ - Hash Chain + Merkle Tree + OpenTimestamp                 │
│ - Permanent retention (no automatic deletion)               │
│ - Bitcoin-anchored proof (legally admissible)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### 1. Spatie Activity Log Foundation

**Why Spatie?**

- ✅ **Mature & Stable:** 5.7k+ stars, 8+ years development, v4.x production-ready
- ✅ **Automatic Model Logging:** Via `LogsActivity` trait
- ✅ **Manual Logging:** Flexible `activity()->log()` API
- ✅ **Extensible:** Custom Activity Model, LogOptions, hooks
- ✅ **Well-Documented:** Comprehensive docs, active community
- ✅ **Laravel Standard:** Used by thousands of Laravel apps

**Base Features:**

```php
// Automatic logging via trait
class Employee extends Model {
    use LogsActivity;

    protected static $logAttributes = ['name', 'email', 'phone'];
    protected static $logOnlyDirty = true;
}

// Automatic log on save
$employee->update(['name' => 'New Name']); // ✅ Logged

// Manual logging
activity()
    ->causedBy(auth()->user())
    ->performedOn($employee)
    ->withProperties(['reason' => 'Annual review'])
    ->log('accessed_salary_data');
```

### 2. Custom Activity Model with Extensions

**Database Schema Extensions:**

```php
// database/migrations/YYYY_MM_DD_extend_activity_log_table.php
Schema::table('activity_log', function (Blueprint $table) {
    // 🔐 Tenant + Organizational Scope Isolation
    $table->unsignedBigInteger('tenant_id')->after('id');
    $table->foreignUuid('organizational_unit_id')->nullable()
        ->after('tenant_id')
        ->constrained('organizational_units')->nullOnDelete();

    // 📊 Request Metadata
    $table->ipAddress('ip_address')->nullable();
    $table->text('user_agent')->nullable();

    // 🔗 Hash Chain (real-time tamper detection)
    $table->string('previous_hash', 64)->nullable();
    $table->string('event_hash', 64)->index();

    // 🌳 Merkle Tree (batch verification)
    $table->string('merkle_root', 64)->nullable();
    $table->unsignedBigInteger('merkle_batch_id')->nullable()->index();
    $table->json('merkle_proof')->nullable();

    // ⏱️ OpenTimestamp (Bitcoin anchoring)
    $table->binary('ots_proof')->nullable();
    $table->timestamp('ots_submitted_at')->nullable();
    $table->timestamp('ots_confirmed_at')->nullable();

    // 📅 Retention Metadata
    $table->boolean('is_orphaned_genesis')->default(false);
    $table->text('orphaned_reason')->nullable();
    $table->timestamp('orphaned_at')->nullable();

    // 🗑️ Soft Delete Support
    $table->softDeletes();

    // 📇 Performance Indexes
    $table->index(['tenant_id', 'created_at']);
    $table->index(['organizational_unit_id', 'created_at']);
    $table->index(['log_name', 'created_at']);
    $table->index(['tenant_id', 'log_name', 'created_at']);
    $table->index(['merkle_batch_id']);
});
```

**Custom Activity Model:**

```php
// app/Models/Activity.php
namespace App\Models;

use Spatie\Activitylog\Models\Activity as BaseActivity;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Database\Eloquent\Concerns\HasUuids;

class Activity extends BaseActivity
{
    use SoftDeletes, HasUuids;

    protected $fillable = [
        ...parent::$fillable,
        'tenant_id',
        'organizational_unit_id',
        'ip_address',
        'user_agent',
        'previous_hash',
        'event_hash',
        'merkle_root',
        'merkle_batch_id',
        'merkle_proof',
        'ots_proof',
        'ots_submitted_at',
        'ots_confirmed_at',
        'is_orphaned_genesis',
        'orphaned_reason',
        'orphaned_at',
    ];

    protected $casts = [
        ...parent::$casts,
        'merkle_proof' => 'array',
        'ots_submitted_at' => 'datetime',
        'ots_confirmed_at' => 'datetime',
        'orphaned_at' => 'datetime',
        'is_orphaned_genesis' => 'boolean',
    ];

    // Security Level Configuration
    protected static array $securityLevels = [
        // Level 1: Standard (1 year retention, soft delete)
        'default' => 1,
        'employee_changes' => 1,
        'shift_management' => 1,

        // Level 2: Security-Critical (3 years, archive)
        'security' => 2,
        'authentication' => 2,
        'rbac_changes' => 2,
        'scope_changes' => 2,

        // Level 3: Legal-Critical (7-10 years, permanent)
        'hr_access' => 3,
        'emergency_access' => 3,
        'contract_change' => 3,
        'works_council_access' => 3,
        'guard_book_event' => 3,
    ];

    protected static function booted()
    {
        parent::booted();

        static::creating(function ($activity) {
            // 1. Auto-inject tenant + org scope
            if ($user = auth()->user()) {
                $activity->tenant_id = $user->tenant_id;
                $activity->organizational_unit_id = request()->get('current_organizational_unit_id');
            }

            // 2. Capture request metadata
            $activity->ip_address = request()->ip();
            $activity->user_agent = request()->userAgent();

            // 3. Build Hash Chain (all logs, real-time)
            $activity->buildHashChain();

            // 4. Schedule Merkle Tree building (Level 2+3)
            $level = static::getSecurityLevel($activity->log_name);
            if ($level >= 2) {
                dispatch(new BuildMerkleTreeBatch($activity))->onQueue('merkle');
            }
        });
    }

    // Hash Chain: Build sequential chain
    protected function buildHashChain(): void
    {
        $previous = static::where('tenant_id', $this->tenant_id)
            ->orderBy('created_at', 'desc')
            ->first();

        $this->previous_hash = $previous?->event_hash;

        $this->event_hash = hash('sha256', json_encode([
            'tenant_id' => $this->tenant_id,
            'log_name' => $this->log_name,
            'description' => $this->description,
            'subject_type' => $this->subject_type,
            'subject_id' => $this->subject_id,
            'causer_type' => $this->causer_type,
            'causer_id' => $this->causer_id,
            'properties' => $this->properties,
            'created_at' => $this->created_at,
            'previous_hash' => $this->previous_hash,
        ]));
    }

    // Hash Chain: Verify integrity
    public function verifyChain(): bool
    {
        if (!$this->previous_hash) {
            return true; // Genesis log
        }

        if ($this->is_orphaned_genesis) {
            return true; // Intentionally orphaned (retention policy)
        }

        // Check active logs first
        $previous = static::where('event_hash', $this->previous_hash)
            ->where('tenant_id', $this->tenant_id)
            ->first();

        if (!$previous) {
            // Check soft deleted logs
            $previous = static::withTrashed()
                ->where('event_hash', $this->previous_hash)
                ->first();
        }

        if (!$previous) {
            // Check archive
            $previous = ActivityArchive::where('event_hash', $this->previous_hash)->first();
        }

        return $previous !== null;
    }

    // Merkle Tree: Verify with Merkle Proof
    public function verifyMerkleProof(): bool
    {
        if (!$this->merkle_root || !$this->merkle_proof) {
            return false;
        }

        $hash = $this->event_hash;

        foreach ($this->merkle_proof as $sibling) {
            if ($sibling['position'] === 'left') {
                $hash = hash('sha256', $sibling['hash'] . $hash);
            } else {
                $hash = hash('sha256', $hash . $sibling['hash']);
            }
        }

        return $hash === $this->merkle_root;
    }

    // OpenTimestamp: Verify Bitcoin anchoring
    public function verifyOpenTimestamp(): bool
    {
        if (!$this->ots_proof || !$this->ots_confirmed_at) {
            return false;
        }

        $proof = OpenTimestamps\Proof::deserialize($this->ots_proof);
        return $proof->verify($this->merkle_root);
    }

    // Get security level
    protected static function getSecurityLevel(string $logName): int
    {
        return static::$securityLevels[$logName] ?? 1;
    }

    // Relationships
    public function organizationalUnit()
    {
        return $this->belongsTo(OrganizationalUnit::class);
    }
}
```

### 3. Security Levels Configuration

**Level Matrix:**

| Level | Log Types         | Retention  | Hash Chain | Merkle Tree | OpenTimestamp | Deletion Strategy                          |
| ----- | ----------------- | ---------- | ---------- | ----------- | ------------- | ------------------------------------------ |
| **1** | Standard Activity | 1 year     | ✅         | ❌          | ❌            | Soft delete → Hard delete after 2 years    |
| **2** | Security-Critical | 3 years    | ✅         | ✅ (hourly) | ❌            | Archive (hash only) → Delete after 5 years |
| **3** | Legal-Critical    | 7-10 years | ✅         | ✅ (daily)  | ✅            | Permanent (no deletion)                    |

**Use Cases per Level:**

```php
// Level 1: Standard Activity Logs
activity('employee_changes')
    ->performedOn($employee)
    ->withProperties(['old' => ['name' => 'Old'], 'new' => ['name' => 'New']])
    ->log('updated');

activity('shift_management')
    ->performedOn($shift)
    ->log('shift_assigned');

// Level 2: Security-Critical Logs
activity('authentication')
    ->causedBy($user)
    ->withProperties(['ip' => $request->ip(), 'success' => false])
    ->log('login_failed');

activity('rbac_changes')
    ->causedBy(auth()->user())
    ->performedOn($user)
    ->withProperties(['role' => 'Manager', 'valid_until' => '2025-12-31'])
    ->log('role_assigned');

activity('scope_changes')
    ->causedBy(auth()->user())
    ->performedOn($user)
    ->withProperties([
        'organizational_unit' => 'Regional GmbH',
        'access_level' => 'admin',
    ])
    ->log('scope_granted');

// Level 3: Legal-Critical Logs
activity('hr_access')
    ->causedBy(auth()->user())
    ->performedOn($employee)
    ->withProperties([
        'accessed_fields' => ['salary', 'contract_data'],
        'reason' => 'Annual review',
    ])
    ->log('accessed_sensitive_data');

activity('emergency_access')
    ->causedBy(auth()->user())
    ->performedOn($employee)
    ->withProperties([
        'permission' => 'employee_document.read',
        'reason' => 'GDPR data subject request - legal requirement',
        'urgency' => 'high',
        'expires_at' => now()->addHours(2),
    ])
    ->log('breaking_glass_activated');

activity('contract_change')
    ->causedBy(auth()->user())
    ->performedOn($contract)
    ->withProperties([
        'old' => ['end_date' => '2025-12-31'],
        'new' => ['end_date' => '2026-06-30'],
        'reason' => 'Contract extension approved',
    ])
    ->log('contract_extended');

activity('works_council_access')
    ->causedBy(auth()->user())
    ->performedOn($employee)
    ->withProperties([
        'accessed_resource' => 'shift_plan',
        'reason' => 'Works council review - BetrVG §99',
    ])
    ->log('br_accessed_data');
```

### 4. Merkle Tree Building

```php
// app/Jobs/BuildMerkleTreeBatch.php
namespace App\Jobs;

use App\Models\Activity;
use App\Models\ActivityArchive;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Support\Collection;

class BuildMerkleTreeBatch implements ShouldQueue
{
    use Queueable;

    public function handle(): void
    {
        // Find tenants with unbatched logs (Level 2+3)
        $tenants = Activity::whereNull('merkle_root')
            ->whereIn('log_name', array_keys(array_filter(
                Activity::$securityLevels,
                fn($level) => $level >= 2
            )))
            ->distinct('tenant_id')
            ->pluck('tenant_id');

        foreach ($tenants as $tenantId) {
            $this->buildTreeForTenant($tenantId);
        }
    }

    protected function buildTreeForTenant(int $tenantId): void
    {
        // Get unbatched logs (Level 2+3, created in batch period)
        $logs = Activity::where('tenant_id', $tenantId)
            ->whereNull('merkle_root')
            ->whereIn('log_name', [/* Level 2+3 log names */])
            ->orderBy('created_at')
            ->get();

        if ($logs->isEmpty()) {
            return;
        }

        // Build Merkle Tree
        $batchId = now()->timestamp;
        $tree = $this->buildTree($logs);

        // Update logs with Merkle Root + Proof
        foreach ($logs as $index => $log) {
            $log->update([
                'merkle_batch_id' => $batchId,
                'merkle_root' => $tree['root'],
                'merkle_proof' => $tree['proofs'][$index],
            ]);
        }

        // Submit Merkle Root to OpenTimestamp (Level 3 only)
        $hasLevel3 = $logs->contains(fn($log) =>
            Activity::getSecurityLevel($log->log_name) === 3
        );

        if ($hasLevel3) {
            dispatch(new SubmitMerkleRootToOpenTimestamp(
                $tenantId,
                $batchId,
                $tree['root']
            ));
        }
    }

    protected function buildTree(Collection $logs): array
    {
        $leaves = $logs->pluck('event_hash')->toArray();
        $tree = [$leaves];
        $proofs = array_fill(0, count($leaves), []);

        while (count($tree[0]) > 1) {
            $level = [];
            $prevLevel = $tree[0];

            for ($i = 0; $i < count($prevLevel); $i += 2) {
                $left = $prevLevel[$i];
                $right = $prevLevel[$i + 1] ?? $left;

                $parent = hash('sha256', $left . $right);
                $level[] = $parent;

                $proofs[$i][] = ['hash' => $right, 'position' => 'right'];
                if ($i + 1 < count($prevLevel)) {
                    $proofs[$i + 1][] = ['hash' => $left, 'position' => 'left'];
                }
            }

            array_unshift($tree, $level);
        }

        return [
            'root' => $tree[0][0],
            'proofs' => $proofs,
        ];
    }
}
```

### 5. Retention & Archiving

**Activity Archive Model:**

```php
// app/Models/ActivityArchive.php
namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class ActivityArchive extends Model
{
    protected $table = 'activity_log_archive';

    protected $fillable = [
        'id',                    // Original activity log ID
        'tenant_id',
        'log_name',
        'created_at',
        'event_hash',
        'previous_hash',
        'merkle_root',
        'merkle_batch_id',
        // NO properties, subject, causer (GDPR!)
    ];

    public $timestamps = false; // Immutable archive
}
```

**Retention Jobs:**

```php
// app/Console/Commands/ApplyRetentionPolicies.php
namespace App\Console\Commands;

use App\Models\Activity;
use App\Models\ActivityArchive;
use Illuminate\Console\Command;

class ApplyRetentionPolicies extends Command
{
    protected $signature = 'activity:apply-retention';

    public function handle(): int
    {
        $this->info('Applying retention policies...');

        // Level 1: Soft delete after 1 year
        $this->handleLevel1Retention();

        // Level 1: Hard delete soft-deleted after 2 years total
        $this->handleLevel1HardDelete();

        // Level 2: Archive after 3 years
        $this->handleLevel2Archiving();

        // Level 2: Delete archived after 5 years total
        $this->handleLevel2Deletion();

        // Level 3: No automatic deletion (permanent retention)

        $this->info('Retention policies applied successfully.');
        return 0;
    }

    protected function handleLevel1Retention(): void
    {
        $count = Activity::whereIn('log_name', ['default', 'employee_changes', 'shift_management'])
            ->where('created_at', '<', now()->subYear())
            ->whereNull('deleted_at')
            ->each(fn($log) => $log->delete()) // Soft delete
            ->count();

        $this->info("Level 1: Soft deleted {$count} logs older than 1 year.");
    }

    protected function handleLevel1HardDelete(): void
    {
        $count = Activity::onlyTrashed()
            ->where('deleted_at', '<', now()->subYear())
            ->each(function ($log) {
                // Mark next log as orphaned genesis if needed
                $nextLog = Activity::where('previous_hash', $log->event_hash)->first();
                if ($nextLog) {
                    $nextLog->update([
                        'previous_hash' => null,
                        'is_orphaned_genesis' => true,
                        'orphaned_reason' => 'Predecessor deleted (retention policy)',
                        'orphaned_at' => now(),
                    ]);
                }

                $log->forceDelete();
            })
            ->count();

        $this->info("Level 1: Hard deleted {$count} soft-deleted logs older than 2 years total.");
    }

    protected function handleLevel2Archiving(): void
    {
        $logs = Activity::whereIn('log_name', ['security', 'authentication', 'rbac_changes'])
            ->where('created_at', '<', now()->subYears(3))
            ->get();

        foreach ($logs as $log) {
            ActivityArchive::create([
                'id' => $log->id,
                'tenant_id' => $log->tenant_id,
                'log_name' => $log->log_name,
                'created_at' => $log->created_at,
                'event_hash' => $log->event_hash,
                'previous_hash' => $log->previous_hash,
                'merkle_root' => $log->merkle_root,
                'merkle_batch_id' => $log->merkle_batch_id,
            ]);

            $log->forceDelete();
        }

        $this->info("Level 2: Archived {$logs->count()} logs older than 3 years.");
    }

    protected function handleLevel2Deletion(): void
    {
        $count = ActivityArchive::where('created_at', '<', now()->subYears(5))
            ->delete();

        $this->info("Level 2: Deleted {$count} archived logs older than 5 years total.");
    }
}
```

### 6. Scoped Access Control

**Policy:**

```php
// app/Policies/ActivityPolicy.php
namespace App\Policies;

use App\Models\User;
use App\Models\Activity;

class ActivityPolicy
{
    public function viewAny(User $user): bool
    {
        return $user->hasPermissionTo('activity_log.read');
    }

    public function view(User $user, Activity $activity): bool
    {
        // 1. Tenant isolation (mandatory)
        if ($activity->tenant_id !== $user->tenant_id) {
            return false;
        }

        // 2. Global logs (no org scope)
        if (!$activity->organizational_unit_id) {
            return $user->hasPermissionTo('activity_log.read_all');
        }

        // 3. Check user has access to organizational unit
        if (!$user->hasAccessToUnit($activity->organizationalUnit)) {
            return false;
        }

        // 4. Check inheritance blocking (CRITICAL!)
        if ($activity->organizationalUnit->blocksPermissionInheritance('activity_log.read')) {
            // Must have DIRECT scope (not inherited)
            return $user->organizationalScopes()
                ->where('organizational_unit_id', $activity->organizational_unit_id)
                ->exists();
        }

        return true;
    }
}
```

**Controller:**

```php
// app/Http/Controllers/Api/V1/ActivityLogController.php
namespace App\Http\Controllers\Api\V1;

use App\Models\Activity;
use App\Http\Resources\ActivityResource;

class ActivityLogController extends Controller
{
    public function index(Request $request)
    {
        $this->authorize('viewAny', Activity::class);

        $query = Activity::query()
            ->where('tenant_id', $request->user()->tenant_id);

        // Filter by organizational scopes
        if (!$request->user()->hasPermissionTo('activity_log.read_all')) {
            $accessibleUnitIds = $request->user()->getAccessibleOrganizationalUnitIds();

            $query->where(function ($q) use ($accessibleUnitIds) {
                $q->whereIn('organizational_unit_id', $accessibleUnitIds)
                  ->orWhereNull('organizational_unit_id');
            });

            // Exclude blocked units (unless direct scope)
            $blockedUnits = OrganizationalUnit::whereJsonContains(
                'inheritance_blocks->blocked_permissions',
                'activity_log.read'
            )->pluck('id');

            $directScopes = $request->user()->organizationalScopes()
                ->pluck('organizational_unit_id');

            $allowedBlockedUnits = $blockedUnits->intersect($directScopes);

            $query->whereNotIn('organizational_unit_id',
                $blockedUnits->diff($allowedBlockedUnits)
            );
        }

        return ActivityResource::collection(
            $query->latest()->paginate(50)
        );
    }

    public function verify(Activity $activity)
    {
        $this->authorize('view', $activity);

        return response()->json([
            'activity_id' => $activity->id,
            'chain_valid' => $activity->verifyChain(),
            'merkle_valid' => $activity->verifyMerkleProof(),
            'ots_valid' => $activity->verifyOpenTimestamp(),
        ]);
    }
}
```

---

## Consequences

### Positive Consequences

✅ **GDPR Compliance:**

- Complete audit trail (Article 30)
- Technical security measures (Article 32)
- Automated retention policies (data minimization)
- Tamper-proof evidence (accountability)

✅ **Legal Admissibility:**

- Cryptographically verifiable integrity
- Bitcoin-anchored timestamps (external trust anchor)
- Independent verification possible
- Suitable for court proceedings

✅ **Organizational Autonomy:**

- Regional subsidiaries can protect logs via inheritance blocking
- Scoped access respects organizational boundaries
- Parent organizations cannot access blocked logs

✅ **Performance:**

- Hash chain built in real-time (O(1) per log)
- Merkle tree batched (hourly/daily, async)
- OpenTimestamp only for critical logs (minimal overhead)
- Efficient indexes for fast queries

✅ **Maintainability:**

- Built on mature Spatie foundation (update-safe)
- Clear 3-tier security model
- Well-documented extension points
- Automated retention via scheduled commands

### Negative Consequences

❌ **Complexity:**

- Three-tier architecture requires understanding
- Multiple integrity mechanisms (chain + tree + timestamp)
- Retention policies need careful configuration

**Mitigation:**

- Comprehensive documentation
- Clear configuration via `$securityLevels` array
- Automated via scheduled commands

❌ **Storage:**

- Hash chain + Merkle proof adds ~100 bytes per log
- OpenTimestamp proof adds ~5 KB (Level 3 only)
- Archive table required for Level 2

**Mitigation:**

- Soft delete reduces immediate storage impact
- Archive stores only hashes (minimal)
- Level 3 retention justified by legal requirements

❌ **Breaking Changes:**

- Extends Spatie's activity_log table (migration required)
- Custom Activity model (config change required)
- Existing logs need backfilling (previous_hash, event_hash)

**Mitigation:**

- Migration with backfill script
- Zero-downtime deployment possible
- Clear upgrade guide

### Risks

**Risk 1: Spatie Major Version Update**

**Probability:** Low (v4.x stable for years)
**Impact:** Medium (may require code adjustments)

**Mitigation:**

- Use official extension points only
- Test updates in staging
- Pin major version in composer.json

**Risk 2: Hash Chain Performance at Scale**

**Probability:** Low (SELECT + INSERT operations standard)
**Impact:** Low (microseconds overhead)

**Mitigation:**

- Index on event_hash
- Use queue for Merkle tree building
- Monitor performance metrics

**Risk 3: Merkle Tree Batching Delay**

**Probability:** Certain (by design)
**Impact:** Low (Level 2+3 verification delayed until batch)

**Mitigation:**

- Hash chain provides immediate tamper detection
- Merkle tree is additional layer
- OpenTimestamp typically takes hours anyway

---

## Implementation Plan

### Phase 1: Foundation (Week 1)

**Tasks:**

- [ ] Install Spatie Laravel Activity Log
- [ ] Publish and customize config
- [ ] Create migration for table extensions
- [ ] Implement custom Activity model
- [ ] Configure security levels matrix
- [ ] Write unit tests for hash chain

**Deliverables:**

- Basic activity logging working
- Hash chain integrity functional
- Tests passing

### Phase 2: Merkle Tree (Week 2)

**Tasks:**

- [ ] Implement BuildMerkleTreeBatch job
- [ ] Add Merkle proof storage
- [ ] Write Merkle verification methods
- [ ] Schedule hourly/daily batching
- [ ] Write unit tests for Merkle tree

**Deliverables:**

- Merkle tree batching working
- Level 2+3 logs get Merkle proofs
- Tests passing

### Phase 3: OpenTimestamp Integration (Week 3)

**Tasks:**

- [ ] Integrate OpenTimestamp PHP library
- [ ] Implement SubmitMerkleRootToOpenTimestamp job
- [ ] Add OTS proof upgrade command
- [ ] Write verification methods
- [ ] Write integration tests

**Deliverables:**

- Level 3 logs get OTS proofs
- Bitcoin anchoring functional
- Tests passing

### Phase 4: Retention Policies (Week 4)

**Tasks:**

- [ ] Create ActivityArchive model + migration
- [ ] Implement ApplyRetentionPolicies command
- [ ] Add soft delete support
- [ ] Add orphaned genesis handling
- [ ] Schedule daily retention job
- [ ] Write retention tests

**Deliverables:**

- Automated retention working
- Archive functional
- Hash chain integrity maintained after deletion

### Phase 5: Scoped Access Control (Week 5)

**Tasks:**

- [ ] Implement ActivityPolicy
- [ ] Add organizational scope filtering
- [ ] Add inheritance blocking checks
- [ ] Create ActivityLogController
- [ ] Write authorization tests

**Deliverables:**

- Scoped access working
- Regional subsidiaries isolated
- Tests passing

### Phase 6: UI & Documentation (Week 6)

**Tasks:**

- [ ] Create audit dashboard (frontend)
- [ ] Add verification UI
- [ ] Write user documentation
- [ ] Write admin guide
- [ ] Write legal verification guide
- [ ] Create deployment guide

**Deliverables:**

- Complete documentation
- User-friendly audit interface

---

## Testing Strategy

### Unit Tests

```php
test('hash chain is built correctly', function () {
    $log1 = Activity::create([...]);
    expect($log1->previous_hash)->toBeNull();
    expect($log1->event_hash)->not->toBeNull();

    $log2 = Activity::create([...]);
    expect($log2->previous_hash)->toBe($log1->event_hash);
});

test('hash chain detects tampering', function () {
    $log1 = Activity::create([...]);
    $log2 = Activity::create([...]);

    // Tamper with log1
    $log1->update(['description' => 'TAMPERED'], ['timestamps' => false]);

    expect($log2->verifyChain())->toBeFalse();
});

test('merkle proof verifies correctly', function () {
    // Build tree with 4 logs
    $logs = Activity::factory()->count(4)->create();
    dispatch_sync(new BuildMerkleTreeBatch());

    $logs->each(fn($log) =>
        expect($log->fresh()->verifyMerkleProof())->toBeTrue()
    );
});

test('soft delete maintains chain integrity', function () {
    $log1 = Activity::create([...]);
    $log2 = Activity::create([...]);

    $log1->delete(); // Soft delete

    expect($log2->verifyChain())->toBeTrue();
});

test('orphaned genesis after hard delete', function () {
    $log1 = Activity::create([...]);
    $log2 = Activity::create([...]);

    $log1->deleteAndRechain();

    expect($log2->fresh()->previous_hash)->toBeNull();
    expect($log2->fresh()->is_orphaned_genesis)->toBeTrue();
});
```

### Integration Tests

```php
test('activity is logged automatically via trait', function () {
    $employee = Employee::create(['name' => 'John Doe']);

    expect(Activity::where('subject_id', $employee->id)->count())->toBe(1);
});

test('tenant isolation is enforced', function () {
    $tenant1User = User::factory()->create(['tenant_id' => 1]);
    $tenant2User = User::factory()->create(['tenant_id' => 2]);

    $log = Activity::create(['tenant_id' => 1, ...]);

    actingAs($tenant1User)->get("/v1/activity-logs/{$log->id}")
        ->assertOk();

    actingAs($tenant2User)->get("/v1/activity-logs/{$log->id}")
        ->assertForbidden();
});

test('organizational scope filtering works', function () {
    $unit1 = OrganizationalUnit::create(['name' => 'Unit 1']);
    $unit2 = OrganizationalUnit::create(['name' => 'Unit 2']);

    $user = User::factory()->create();
    $user->organizationalScopes()->create([
        'organizational_unit_id' => $unit1->id,
        'access_level' => 'read',
    ]);

    $log1 = Activity::create(['organizational_unit_id' => $unit1->id, ...]);
    $log2 = Activity::create(['organizational_unit_id' => $unit2->id, ...]);

    $response = actingAs($user)->get('/v1/activity-logs');

    expect($response->json('data'))->toHaveCount(1);
    expect($response->json('data.0.id'))->toBe($log1->id);
});

test('inheritance blocking prevents parent access', function () {
    $holding = OrganizationalUnit::create(['name' => 'Holding']);
    $regional = OrganizationalUnit::create([
        'name' => 'Regional GmbH',
        'parent_id' => $holding->id,
        'inheritance_blocks' => [
            'blocked_permissions' => ['activity_log.read'],
        ],
    ]);

    $holdingAdmin = User::factory()->create();
    $holdingAdmin->organizationalScopes()->create([
        'organizational_unit_id' => $holding->id,
        'access_level' => 'admin',
        'include_descendants' => true,
    ]);

    $log = Activity::create(['organizational_unit_id' => $regional->id, ...]);

    actingAs($holdingAdmin)->get("/v1/activity-logs/{$log->id}")
        ->assertForbidden();
});
```

### Security Tests

```php
test('cannot access other tenant logs', function () {
    $log = Activity::create(['tenant_id' => 1, ...]);
    $user = User::factory()->create(['tenant_id' => 2]);

    actingAs($user)->get("/v1/activity-logs/{$log->id}")
        ->assertForbidden();
});

test('cannot modify activity logs', function () {
    $log = Activity::create([...]);
    $user = User::factory()->admin()->create();

    actingAs($user)->patch("/v1/activity-logs/{$log->id}", ['description' => 'HACKED'])
        ->assertMethodNotAllowed();
});

test('hash chain detects injection attacks', function () {
    $log1 = Activity::create([...]);
    $log2 = Activity::create([...]);

    // Attacker tries to inject fake log
    DB::table('activity_log')->insert([
        'id' => Str::uuid(),
        'tenant_id' => $log1->tenant_id,
        'event_hash' => 'FAKE_HASH',
        'previous_hash' => $log1->event_hash, // Try to inject between log1 and log2
        'created_at' => now()->subMinute(),
    ]);

    // log2 still points to log1, not fake log
    expect($log2->verifyChain())->toBeTrue();
});
```

---

## Related ADRs

- **ADR-002:** OpenTimestamp for Audit Trail (integrates with Level 3 logs)
- **ADR-005:** RBAC Design Decisions (role changes are logged)
- **ADR-007:** Organizational Structure Hierarchy (scope-based log access)
- **ADR-008:** User-Based Tenant Resolution (tenant isolation for logs)
- **ADR-009:** Permission Inheritance Blocking & Super-Admin Privileges (emergency access is logged)

---

## References

### Legal & Compliance

- **GDPR Article 30:** Records of Processing Activities
- **GDPR Article 32:** Security of Processing
- **GDPR Article 5(1)(e):** Storage Limitation
- **German BewachV §21:** Buchführung und Aufbewahrung (until end of 3rd following calendar year)
- **BetrVG §87, §99:** Works Council Co-Determination Rights

### Technical Standards

- **NIST SP 800-53:** AU-2 (Audit Events), AU-9 (Protection of Audit Information)
- **ISO/IEC 27001:2013:** A.12.4.1 (Event Logging), A.12.4.2 (Protection of Log Information)
- **OWASP Logging Cheat Sheet:** Secure logging best practices

### External Documentation

- [Spatie Laravel Activity Log Documentation](https://spatie.be/docs/laravel-activitylog)
- [OpenTimestamp Documentation](https://opentimestamps.org/)
- [Merkle Tree Wikipedia](https://en.wikipedia.org/wiki/Merkle_tree)
- [Hash Chain Wikipedia](https://en.wikipedia.org/wiki/Hash_chain)

---

## Open Questions

**Question 1:** Should we log API token usage (bearer token authentication)?

**Pros:**

- Security audit trail
- Detect compromised tokens
- Track token usage patterns

**Cons:**

- High volume (every API request)
- Performance impact
- Storage cost

**Decision:** Defer to Phase 7. Consider sampling (log 1% of requests) or only failed auth attempts.

---

**Question 2:** Should we provide a public verification API for external auditors?

**Use Case:** Court/auditor wants to verify log integrity without SecPal credentials.

**Approach:**

```
GET /api/public/activity-logs/{id}/verify
→ Returns: event_hash, merkle_proof, ots_proof
→ Auditor can verify independently
```

**Decision:** Implement in Phase 6 (UI & Documentation).

---

**Question 3:** Should we support log export for data portability (GDPR Article 20)?

**Requirements:**

- Export user's activity logs in machine-readable format
- Include verification data (hashes, proofs)
- Respect retention policies (no deleted logs)

**Decision:** Implement in Phase 6 with CSV/JSON export formats.

---

## Approval

**Author:** GitHub Copilot (AI Assistant)
**Date:** 2025-12-21

**Review Required By:**

- [ ] Security Team Lead
- [ ] Data Protection Officer (DPO)
- [ ] CTO / Technical Architect
- [ ] Legal Counsel (GDPR compliance)

**Approval Status:** Pending Review

---

## Changelog

- **2025-12-21:** Initial draft created
- **2025-12-21:** Added comprehensive implementation details
- **2025-12-21:** Added testing strategy and security considerations
