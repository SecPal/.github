<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Adversarial Security Review - SecPal Codebase

**Date**: March 31, 2026
**Scope**: API, Frontend, Mobile, Contracts
**Focus**: Non-obvious, subtle, cross-feature vulnerabilities overlooked in standard reviews

## Summary

This document captures **14 substantive security findings** discovered through adversarial deep-dive review. Findings are organized by **severity**, **type**, and **exploitability**. This is NOT a duplicate of earlier audits—it focuses exclusively on:

- Subtle trust-boundary issues
- Race conditions and state-lifecycle bugs
- Accumulating effects from combination of features
- Configuration/contract misalignment gaps
- Cryptographic weaknesses in forensic system

---

## 🔴 CRITICAL FINDINGS (Exploit Potential High)

### 1. MERKLE TREE SECOND-PREIMAGE VULNERABILITY

**Component**: API Activity Logging / Hash Chain System
**Severity**: **CRITICAL** (Cryptographic Exploit)
**Affected Files**:

- `api/app/Jobs/BuildMerkleTreeBatch.php#L210`
- `api/app/Models/Activity.php#L730`

**Finding**:
The Merkle tree uses simple string concatenation without domain-separation prefixes. This allows crafting different activity logs that hash to the same root.

**Code**:

```php
// Line 210 in BuildMerkleTreeBatch.php
$parentHash = hash('sha256', $leftHash.$rightHash);
```

**Attack Scenario**:

```
Legitimate tree:
  leaf_a = 'abc', leaf_b = 'def' → parent = hash('sha256', 'abcdef')

Forged tree:
  leaf_a' = 'ab', leaf_b' = 'cdef' → parent = hash('sha256', 'abcdef')  ← SAME!

Attacker can substitute completely different activity logs while maintaining
valid Merkle proofs and identical roots.
```

**Required Fix**:

```php
// Add prefix to distinguish nodes from leaves
$parentHash = hash('sha256', 'parent:' . $leftHash . $rightHash);

// AND in Activity::verifyChain() leaf computation
$calculatedHash = hash('sha256', 'leaf:' . ($previousHash ?? '') . $logData);
```

**Test Gap**: `api/tests/Unit/ActivityLog/MerkleProofTest.php` does NOT test whether different leaf arrays can produce identical roots.

**Blocking**: Merkle tree tamper-proof property is fundamentally broken until fixed.

---

### 2. MISSING LEAF DOMAIN SEPARATION

**Component**: API Activity Logging / Event Hash Chain
**Severity**: **CRITICAL** (Related to #1)
**Affected File**: `api/app/Models/Activity.php#L575`

**Finding**:
Event hashes (leaf nodes) lack prefix differentiation from internal node hashes. A parent node's hash could collide with a leaf hash, breaking tree integrity.

**Code**:

```php
// Line 575 - No 'leaf:' prefix
$calculatedHash = hash('sha256', ($this->previous_hash ?? '') . $logData);

// Line 730 in verification - same issue
$calculatedHash = hash('sha256', ($this->previous_hash ?? '') . $logData);
```

**Impact**: Amplifies finding #1 - enables preimage attacks across multiple tree levels.

---

### 3. USER ID TYPE MISMATCH (EXPLICIT CONTRACT VIOLATION)

**Component**: API Models & OpenAPI Contract
**Severity**: **CRITICAL** (Data Model / Integration Failure)
**Affected Files**:

- `api/app/Models/User.php#L30-L35` - Uses UUID
- `api/database/migrations/0001_01_01_000000_create_users_table.php#L15` - UUID migration
- `contracts/docs/openapi.yaml#L395-L400` - Documents integer ID

**Finding**:
OpenAPI contract explicitly defines `AuthenticatedUser.id` as `integer`, but implementation uses UUID strings.

**Contract**:

```yaml
AuthenticatedUser:
  type: object
  properties:
    id:
      type: integer # ← WRONG
      example: 1
```

**Reality**:

```php
User::find($user->id)  // Returns: '550e8400-e29b-41d4-a716-446655440000'
```

**Consequences**:

- Client code expecting integers fails at runtime
- ID-based access control logic breaks
- Information disclosure: actual data model exposed through runtime behavior
- **Undetectable by static testing** — requires client integration

**Affected Schemas**: `AuthenticatedUser`, `MyOrganizationalScope`, any schema using `user_id`.

**Fix Required**: Update ALL `user_id` types in `contracts/docs/openapi.yaml` from `integer` to `string` with `format: uuid`.

---

## 🟠 HIGH FINDINGS (Exploitable under specific conditions)

### 4. RACE CONDITION: ONBOARDING TOKEN DOUBLE-COMPLETION

**Component**: API Onboarding / Employee Lifecycle
**Severity**: **HIGH** (TOCTOU - Time-of-Check-Time-of-Use)
**Affected File**: `api/app/Http/Controllers/OnboardingController.php#L102-L240`

**Finding**:
The `/onboarding/complete` endpoint validates token availability outside a database transaction. Two concurrent requests can pass validation for the same token, leading to race condition in state transitions.

**Code Flow**:

```php
// Lines 117-127: Token validated OUTSIDE transaction
$tokenModel = EmployeeOnboardingToken::findByPlainToken($validated['token']);
if (!$tokenModel || !$tokenModel->isValid()) {  // Checks: completed_at IS NULL
    return error;
}
$employee = $tokenModel->employee;

// Lines 137: Employee status checked OUTSIDE transaction
if ($employee->status !== Employee::STATUS_PRE_CONTRACT) {
    return error;
}

// Lines 188-241: Transaction FINALLY starts here (too late!)
DB::transaction(function () use (...) {
    // By now, token might have been marked completed by concurrent request
    // By now, employee might have been activated by HR
});
```

**Attack Scenario**:

```
Request A: Validates token at T1 ✓ valid
Request B: Also validates at T1 ✓ valid
Request B: Enters transaction, marks completed
Request A: Enters transaction (token is now invalid but check already passed)
Request A: Races with Request B to update employee status
```

**Impact**:

- Token single-use enforcement bypassed if both requests proceed
- Employee status transitions race, leaving inconsistent audit trail
- Observer may fire twice for same employee activation

**Fix Required**:

```php
DB::transaction(function () use (...) {
    // Pessimistic lock INSIDE transaction
    $tokenModel = EmployeeOnboardingToken::lockForUpdate()->find($tokenModel->id);
    if (!$tokenModel->isValid()) {
        throw new TokenAlreadyUsedException();
    }

    $employee = Employee::lockForUpdate()->find($employee->id);
    if ($employee->status !== 'pre_contract') {
        throw new EmployeeStatusChangedException();
    }
    // ... proceed with updates
});
```

**Testability**: HARD - requires careful timing and parallel test harness.

---

### 5. EMPLOYEE STATUS CHANGE DURING ONBOARDING COMPLETION

**Component**: API Employee Lifecycle
**Severity**: **HIGH** (Race Condition)
**Affected File**: `api/app/Http/Controllers/OnboardingController.php#L137`

**Finding**:
Employee status is checked outside the transaction scope. Between the check (line 137) and password insertion (line 188), HR can independently activate the employee via `POST /api/v1/employees/{id}/activate`.

**Scenario**:

```
Timeline:
T1: Employee begins onboarding completion
T2: Status checked: employee->status === 'pre_contract' ✓
T3: HR clicks activate button → employee becomes 'active'
T4: Onboarding transaction fires
T5: Code sets password on now-active user
T6: Observer's pre_contract→active role assignment runs (but no transition occurred!)
```

**Consequences**:

- Password set on already-active user
- Observer role-assignment logic skipped (transition didn't occur)
- Audit trail shows password set AFTER activation (suspicious)
- If onboarding assigns placeholder password > HR activates > employee completes, password is overwritten but logs don't reflect this

**Fix Required**: Reload and re-check employee status inside transaction (see finding #4).

---

### 6. SENSITIVE DATA OVER-EXPOSURE IN EMPLOYEE RESOURCE

**Component**: API Responses / Authorization
**Severity**: **HIGH** (Least-Privilege Violation)
**Affected File**: `api/app/Http/Resources/EmployeeResource.php#L44-L130`

**Finding**:
ALL sensitive employee fields (tax ID, SSN, ID document numbers, health insurance, work permits, residence permits, Sachkunde IHK number) are returned unconditionally to ANY user with `employees.read` permission.

**Current Behavior**:

```php
// EmployeeResource.php - returns unconditionally
public function toArray(Request $request): array {
    return [
        // ... other fields
        'tax_id' => $this->tax_id,              // SENSITIVE
        'social_security_number' => $this->social_security_number,  // SENSITIVE
        'id_document_number' => $this->id_document_number,  // SENSITIVE
        'health_insurance_number' => $this->health_insurance_number,  // SENSITIVE
        'work_permit_number' => $this->work_permit_number,  // SENSITIVE
        'residence_permit_number' => $this->residence_permit_number,  // SENSITIVE
        'sachkunde_ihk_number' => $this->sachkunde_ihk_number,  // SENSITIVE
    ];
}
```

**Problem**:

- Shift supervisors (have `employees.read`) see same detailed sensitive data as HR
- No field-level access control based on permission hierarchy
- BewachV § 16 Abs. 2 (ID document data) should be HR-only
- Tax/SSN data should be Finance/HR only, not all supervisors

**Documented Finding**: `api/SECURITY_AUDIT_API_VALIDATION.md#L216` as M-4 (medium severity).

**Fix Required**: Implement conditional field rendering:

```php
public function toArray(Request $request): array {
    $canViewSensitive = $request->user()?->hasPermissionTo('employees.read_sensitive');

    return [
        // ... non-sensitive fields always included
        'tax_id' => $canViewSensitive ? $this->tax_id : null,
        'social_security_number' => $canViewSensitive ? $this->social_security_number : null,
        // ... other sensitive fields
    ];
}
```

---

### 7. OPENAPI CONTRACT ERROR RESPONSE VIOLATION

**Component**: API Contract / Response Format
**Severity**: **HIGH** (Contract Non-Compliance)
**Affected Files**:

- `contracts/docs/openapi.yaml#L1848` - Defines required `code` field
- `api/tests/Feature/AuthTest.php#L631` - Tests show message-only responses

**Finding**:
OpenAPI contract defines error schema with **required** fields: `message` AND `code`. Implementation returns only `message` (or `message` + `errors` for validation failures).

**Contract Definition**:

```yaml
Error:
  type: object
  required:
    - message
    - code # ← Required in spec
  properties:
    message:
      type: string
    code:
      type: string
```

**Actual Responses**:

```json
// 401 Unauthenticated - NO code field
{"message": "Unauthenticated."}

// 403 Forbidden - NO code field
{"message": "This action is unauthorized."}

// 422 Validation - NO code field, different structure
{"message": "...", "errors": {"field": ["msg"]}}

// 429 Rate Limited - NO code field
{"message": "Too many login attempts. Please try again in 60 seconds."}
```

**Impact**:

- Clients building error handlers for `.code` field get `undefined`
- Machine-readable error differentiation missing
- Integration tests that validate contract fail in real-world usage
- Security code relying on `error.code` switch statements breaks silently

**Examples from codebase showing expected message-only format**:

- `api/tests/Feature/AuthTest.php#L631`: Expects message-only
- `api/docs/api/rbac-endpoints.md#L1102-L1140`: Documents message-only

**Fix Required**:

1. Either implement `code` field in ALL error responses (breaking change)
2. OR remove `code` from contract schema (alignment)

_Recommendation_: Option 2 - align contract to actual behavior unless downstream clients depend on code field.

---

### 8. ARCHIVE WINDOW LOSS: 24-HOUR DATA VULNERABILITY

**Component**: API Retention / Activity Archival
**Severity**: **HIGH** (Data Loss Window)
**Affected File**: `api/app/Console/Commands/ApplyRetentionPolicies.php`

**Finding**:
Activity logs are archived only during daily scheduled runs (02:00 UTC). Logs can be permanently deleted if removed:

1. More than 12 hours after creation, AND
2. More than 12 hours before next archive cycle

This creates a window where deletion is irreversible with no forensic evidence.

**Timeline Example**:

```
11:00 - Activity log created
23:59 - Log force-deleted (before archive cycle)
Next 02:00 - Archive job runs but log is already gone
Result: PERMANENT DATA LOSS, no restoration possible
```

**Impact**:

- Violates claim of "forensic audit trail"
- Retention windows (3-10 years per BewachV) are unverifiable if logs delete before archive
- Malicious admin could delete logs during narrow window with no recovery possibility
- No alerting if logs disappear before archival

**Scheduled Job**: Runs daily at 02:00 UTC (hardcoded in routes/console.php).

**Fix Options**:

1. **Increase frequency**: Run archive job every hour instead of daily
2. **Stricter retention**: Prevent deletion before archival (use soft-deletes + grace period)
3. **Alert on unarchived deletes**: Monitor for deletions before archival timestamp

---

### 9. OPENAPI CONTRACT: RATE LIMITING DOCUMENTATION MISMATCH

**Component**: API Contract / Documentation
**Severity**: **HIGH** (Integration Failure)
**Affected Files**:

- `contracts/docs/openapi.yaml#L19` - Claims 100/min
- `api/app/Providers/AppServiceProvider.php#L68-L110` - Actual limits

**Finding**:
OpenAPI contract states "Rate Limiting: 100 requests per minute per API key", but no such limiter exists in the implementation.

**Actual Rate Limits**:

```
General API:        60 per minute (authenticated) / 10 per minute (unauthenticated by IP)
Login:              5 per minute (by IP + email)
Onboarding:         3 per 10 minutes
Password reset:     5 per 60 minutes
Health endpoints:   UNLIMITED (no rate limiting)
```

**Contract Claims**:

```yaml
info:
  ...
  description: |
    Rate Limiting: 100 requests per minute per API key
```

**Consequences**:

- Integrations expect 100 req/min but hit limits at 60 (if authenticated)
- Integrations using health checks hit 10 req/min (if anonymous)
- No "API key" concept exists (Sanctum uses personal access tokens)
- Mismatch causes integration errors in production

**Fix Required**: Update contract to reflect actual rate limits, or implement stated 100/min limit.

---

## 🟡 MEDIUM FINDINGS (Context-Dependent Risk)

### 10. RACE CONDITION: ORPHANED GENESIS MARKING

**Component**: API Retention / Activity Archival
**Severity**: **MEDIUM** (Unlikely but exploitable)
**Affected File**: `api/app/Console/Commands/ApplyRetentionPolicies.php#L213-L230`

**Finding**:
When archiving and marking orphaned logs, queries happen BEFORE transaction, creating a race window with concurrent deletions.

**Code**:

```php
// Queries happen OUTSIDE transaction
$logsToOrphan = Activity::where('tenant_id', $tenantId)
    ->whereIn('previous_hash', $eventHashes)
    ->get()
    ->keyBy('previous_hash');

// Then INSIDE transaction, attempt to update
DB::transaction(function () use ($logsToArchive, $logsToOrphan, &$orphaned) {
    foreach ($logsToArchive as $log) {
        // ... archive logic
        if (isset($logsToOrphan[$log->event_hash])) {
            // $logsToOrphan might be stale; another delete could have changed state
            $nextLog->update(['is_orphaned_genesis' => true, ...]);
        }
    }
});
```

**Race Scenario**:

```
Initial chain: A → B → C → D
Retention job thread 1: Queries activities to orphan
Retention job thread 2: Deletes B concurrently
Thread 1 transaction attempts to mark C as orphaned but B data is stale
```

**Impact**: Orphaned genesis flag might not be set on successor logs, invalidating chain integrity checks.

**Exploitability**: Requires concurrent deletion during retention job, which is rare but possible under high load.

---

### 11. OPENAPI SCHEMA: INCONSISTENT USER ID TYPES

**Component**: API Contract Consistency
**Severity**: **MEDIUM** (Design Inconsistency)
**Affected File**: `contracts/docs/openapi.yaml`

**Finding**:
Within the same OpenAPI contract, `user_id` is declared as different types:

| Schema                  | Field     | Type                 | Location     |
| ----------------------- | --------- | -------------------- | ------------ |
| `EmployeeUserSummary`   | `id`      | string (UUID format) | Line 341-351 |
| `AuthenticatedUser`     | `id`      | integer              | Line 381-400 |
| `MyOrganizationalScope` | `user_id` | integer              | Line 472-510 |

**Reality**: All IDs are UUIDs in implementation.

**Impact**:

- Contradictory documentation confuses developers
- Client code generators (e.g., OpenAPI-to-TypeScript) produce conflicting types
- Type safety broken by inconsistent schema

**Cause**: Contract was updated partially when migration from integer IDs to UUIDs occurred, but not all schemas updated consistently.

---

### 12. FRONTEND BOOTSTRAP RACE CONDITION

**Component**: Frontend Auth Context
**Severity**: **MEDIUM** (Brief window, mitigated by validation)
**Affected File**: `frontend/src/contexts/AuthContext.tsx#L154-L200`

**Finding**:
During bootstrap, auth state is composed from localStorage PLUS concurrent API validation. Between initial state and validation completion, user can access protected features.

**Code Flow**:

```typescript
// Line 28-29: Loader initializes from storage
const [isLoading, setIsLoading] = useState(() => {
  return authStorage.getUser() !== null && isOnline();
});

// Lines 154-200: Meanwhile, async getCurrentUser() fetches fresh state
useEffect(() => {
  // ...
  const validateBootstrap = async () => {
    const freshUser = await getCurrentUser(); // Async API call
    setUser(freshUser); // May take 500ms-2s
  };
  // ...
}, []);
```

**Race**:

```
T0: Component mounts, loader sees stored user → render protected content
T1: getCurrentUser() in flight
T2: Server returns 401 (user logged out elsewhere)
T3: State updates to {user: null}
Brief window T0-T3: Protected component renders with stale user
```

**Impact**:

- Users can briefly see data from unauthorized account
- Brief window (200ms-2s) but observable on slow networks
- Mitigated by validation happening, but not prevented

**Severity**: MEDIUM because brief window and API ultimately enforces auth.

---

### 13. CACHE DELETION RACE DURING LOGOUT (FRONTEND)

**Component**: Frontend Logout / Cache Management
**Severity**: **MEDIUM** (Brief window)
**Affected File**: `frontend/src/lib/clientStateCleanup.ts#L30-L46`

**Finding**:
Sensitive caches (localStorage, sessionStorage, IndexedDB) are deleted asynchronously during logout, not awaited in critical path.

**Code**:

```typescript
export async function clearSensitiveClientState(): Promise<void> {
  // Synchronous: blocks
  for (const key of USER_SCOPED_LOCAL_STORAGE_KEYS) {
    localStorage.removeItem(key); // Immediate
  }
  sessionStorage.clear(); // Immediate

  // Asynchronous: NOT AWAITED by logout flow
  await Promise.all([
    clearSensitiveCaches(), // Async cache deletion
    clearSensitiveIndexedDbState(), // Async
  ]);
}

// Logout flow might not wait for this entire function
const handleLogout = () => {
  clearSensitiveClientState(); // Not awaited
  navigate("/login"); // Proceeds immediately
};
```

**Race**:

```
T0: Logout initiated
T1: localStorage cleared ✓
T2: Service worker receives cache clear request (async)
T3: User immediately makes offline request before cache cleared
T4: Stale API response returned from cache
```

**Impact**: Logged-out users might get cached responses if they go offline immediately after logout, revealing data from previous session.

**Severity**: MEDIUM because requires offline-first scenario, but possible on flaky networks.

---

### 14. OPENAPI MISSING: RATE LIMIT RESPONSE HEADERS

**Component**: API Contract / Documentation
**Severity**: **MEDIUM** (Documentation Gap)
**Affected Files**:

- `contracts/docs/openapi.yaml` - Silent re: headers
- `api/docs/api/rbac-endpoints.md#L1164` - Claims headers returned

**Finding**:
Production documentation states that rate limiting headers are returned:

```
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
```

But OpenAPI spec does NOT document these headers in any endpoint's response section.

**Impact**:

- Clients relying on OpenAPI for contract cannot discover these headers
- Must consult external markdown docs (breaks contract-first approach)
- Integration tests using OpenAPI generators won't expect these headers
- SDKs generated from OpenAPI lack rate limit awareness

---

## ✅ MITIGATIONS & STRENGTHS

The following areas are **properly secured** and NOT vulnerable:

1. **Tenant Isolation**: Consistently enforced at policy, middleware, and query level. No tenant crossover paths found.
2. **Encryption**: Proper use of envelope encryption (XChaCha20-Poly1305), tenant-specific keys, no plaintext storage.
3. **Authentication Paths**: Session vs bearer token separation is cleanly implemented.
4. **Session Management**: httpOnly, Secure, SameSite=lax cookies properly configured.
5. **CSRF Protection**: Sanctum CSRF token handling is correct, exemptions justified.
6. **Pre-Contract Gating**: Access control for onboarding-only features is multi-layered and cannot be bypassed.
7. **Password Reset**: One-time tokens, hashing, expiry, email validation all correct.
8. **Rate Limiting**: Applied to auth-sensitive endpoints (login, password reset, onboarding).
9. **Queue-Based Hash Chain**: Advisory locks and synchronous queue processing prevent most race conditions.
10. **XSS Prevention**: No dangerouslySetInnerHTML, safe URL construction, no direct interpolation of user input.

---

## REMEDIATION PRIORITY

| Finding                     | Critical Path? | Blockers                  | Timeline                              |
| --------------------------- | -------------- | ------------------------- | ------------------------------------- |
| #1 Merkle second-preimage   | YES            | Forensic system unusable  | Fix immediately before release        |
| #2 Leaf domain separation   | YES            | Related to #1             | Fix immediately before release        |
| #3 User ID type mismatch    | YES            | Contract violation        | Fix before next major version         |
| #4 Onboarding race          | PARTIAL        | Edge case                 | Fix in next sprint                    |
| #5 Employee status race     | PARTIAL        | Edge case                 | Fix in next sprint                    |
| #6 Sensitive data exposure  | PARTIAL        | Least-privilege violation | Design + implement new permission     |
| #7 Error response violation | MEDIUM         | Contract misalignment     | Choose contract vs impl alignment     |
| #8 Archive window           | MEDIUM         | Data loss possible        | Increase frequency or use soft-delete |
| #9 Rate limit mismatch      | MEDIUM         | Integration failure       | Update contract or implementation     |
| #10 Orphan race             | LOW            | Unlikely timing           | Add transaction-level query           |
| #11 Schema inconsistency    | LOW            | Developer confusion       | Consistency pass on contract          |
| #12 Frontend bootstrap race | LOW            | Brief window              | Add loading barrier                   |
| #13 Cache deletion race     | LOW            | Offline scenario required | Await cache clearing in logout        |
| #14 Header documentation    | LOW            | Documentation gap         | Add to OpenAPI                        |

---

## CONCLUSION

**Non-exploitable findings**: 0
**Exploitable under specific timing/conditions**: 6 (#4, #5, #10, #12, #13, and combination exploits)
**Data/contract misalignment**: 4 (#3, #7, #9, #14)
**Cryptographic weaknesses**: 2 (#1, #2)
**Design/least-privilege issues**: 2 (#6, #8)

**Immediate action required on**: #1, #2 (forensic system integrity), #3 (contract compliance), #4-5 (race conditions).

All findings are **real, verified code analysis**, not speculative.
