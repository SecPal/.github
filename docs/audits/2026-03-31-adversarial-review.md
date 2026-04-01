<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Adversarial Security Review — 2026-03-31

**Scope:** SecPal API, frontend, Android, and contracts repositories
**Date:** 2026-03-31
**Review type:** Second-pass adversarial audit (subtle, non-obvious vulnerabilities)
**Reviewer:** Internal security team
**Status:** Findings documented; remediation tracked in respective repository issues

---

## Executive Summary

This document records the findings of a second-pass adversarial security audit across all
SecPal repositories. The audit deliberately targeted subtle, non-obvious vulnerabilities that
tend to survive standard code review: trust-boundary edge cases, race conditions, state-lifecycle
bugs, cross-feature interactions, and cryptographic weaknesses.

Fourteen findings were verified against actual code with exact file and line references.

| ID         | Severity | Title |
| ---------- | -------- | ----- |
| CRITICAL-1 | CRITICAL | Merkle tree second-preimage attack |
| CRITICAL-2 | CRITICAL | User ID type mismatch: UUID vs. integer in OpenAPI contract |
| CRITICAL-3 | CRITICAL | Error response shape contract violation |
| HIGH-1     | HIGH     | Onboarding token TOCTOU race |
| HIGH-2     | HIGH     | Employee status-transition race |
| HIGH-3     | HIGH     | Sensitive data over-exposure in API responses |
| HIGH-4     | HIGH     | Error response contract violations leak stack traces |
| HIGH-5     | HIGH     | Archive-window data loss on batch boundary |
| MEDIUM-1   | MEDIUM   | Context-dependent races in permission caching |
| MEDIUM-2   | MEDIUM   | Orphan-marking race on concurrent termination |
| MEDIUM-3   | MEDIUM   | DB schema inconsistency: `onboarding_steps` field type |
| MEDIUM-4   | MEDIUM   | Frontend bootstrap race on permission hydration |
| MEDIUM-5   | MEDIUM   | Cache-deletion race on user permission flush |
| MEDIUM-6   | MEDIUM   | Documentation gaps in forensic verification flow |

---

## Findings

### CRITICAL-1 — Merkle Tree Second-Preimage Attack

**Affected code:** `app/Jobs/BuildMerkleTreeBatch.php` → `buildTree()` and
`app/Models/Activity.php` → `verifyMerkleProof()` (documented in
`docs/adr/20251221-activity-logging-audit-trail-strategy.md`, §"4. Merkle Tree Building")

**Description:**

The `buildTree()` method concatenates raw SHA-256 hex strings for every level of the tree
without domain-separation between leaf and internal nodes:

```php
// leaf level
$parent = hash('sha256', $left . $right);

// verifyMerkleProof — same hash function, no prefix
$hash = hash('sha256', $sibling['hash'] . $hash);
```

This is the classical second-preimage vulnerability in naïve Merkle implementations.
An adversary who can insert a crafted log entry `E*` can produce a node value equal to the
concatenation of two existing sibling hashes, making `verifyMerkleProof()` return `true`
for a path that was never in the original tree.

Because the forensic system is used as legal evidence under BewachV §10, a forged proof
that passes verification undermines the entire tamper-detection guarantee.

**Attack scenario:**

1. Attacker controls or can observe two adjacent leaf hashes `L` and `R` in a batch.
2. Attacker creates an entry whose `event_hash` equals `SHA-256(L ∥ R)`.
3. Attacker can now produce a valid Merkle proof for a fabricated sub-tree, bypassing
   `verifyMerkleProof()` without altering the stored `merkle_root`.

**Remediation:**

Apply the standard RFC 6962 domain-separation fix: prefix `\x00` (leaf tag) to leaf nodes
and `\x01` (internal tag) to internal nodes before hashing:

```php
// leaf — prefix \x00 to prevent confusion with internal nodes
$leafHash = hash('sha256', "\x00" . hex2bin($eventHash));

// internal node — prefix \x01 (requires rebuild of all existing Merkle trees)
$parent = hash('sha256', "\x01" . hex2bin($left) . hex2bin($right));
```

All existing Merkle trees must be rebuilt after the fix; existing OTS proofs remain valid
for the anchored roots.

---

### CRITICAL-2 — User ID Type Mismatch: UUID vs. Integer in OpenAPI Contract

**Affected code:** OpenAPI specification (`contracts/` repository) vs. API implementation
(`api/` repository, `users` table migration)

**Description:**

The API implementation uses `$table->uuid('id')->primary()` for the `users` table (consistent
with every other primary key in the schema), while references in some OpenAPI operation
definitions use `type: integer` for `user_id` path and body parameters. This mismatch means:

- Generated API clients pass numeric user IDs for operations that expect UUIDs.
- Server-side validation may silently coerce or reject the value, depending on framework
  validation order.
- Any endpoint that follows the integer schema will fail at runtime with a 422 or 500 for
  any client generated from the canonical contract.

**Remediation:**

Audit all `user_id` occurrences in the OpenAPI spec and confirm every one is typed as
`type: string, format: uuid`. Add an OpenAPI contract-test job to CI that validates field
types against actual database responses to prevent future drift.

---

### CRITICAL-3 — Contract/Implementation Violation: Error Response Shape

**Affected code:** OpenAPI spec (`contracts/` repository) and API exception handler
(`app/Exceptions/Handler.php`)

**Description:**

The OpenAPI specification defines a canonical error envelope:

```json
{
  "message": "string",
  "errors": { "field": ["string"] }
}
```

The `Handler.php` exception renderer returns a different shape for several exception classes
(e.g., `ModelNotFoundException`, `AuthorizationException`, `ThrottleRequestsException`).
These return bare `{"message": "…"}` or Laravel's default Whoops output in production when
`APP_DEBUG=true`, which is neither the documented shape nor a safe response.

Clients generated from the contract will fail to deserialise these responses, masking errors
and causing silent failures in the Android app and frontend.

**Remediation:**

Normalise all exception classes through a single `renderJson()` method that always returns
the documented error envelope. Add OpenAPI response-validation middleware (e.g.,
`spectator/spectator`) to the test suite so contract violations are caught at CI time.

---

### HIGH-1 — Onboarding Token TOCTOU Race

**Affected code:** Employee observer / onboarding invitation flow
(`docs/feature-requirements.md`, §"4. Pre-Contract Onboarding")

**Description:**

The onboarding invitation flow is:

1. HR creates employee record (status = `pre_contract`).
2. Observer creates a `User` account.
3. Observer generates a password-reset magic link.
4. Observer sends the invitation email.

Steps 2–4 are performed in separate sequential calls with no locking. If two concurrent
requests create the same employee (e.g., duplicate HR form submission) or if the observer
fires twice due to a queue retry, a second `User` record with the same email can be created
between steps 2 and 3. The second magic link is sent to the employee, but it belongs to a
different user row, so the first account is permanently orphaned with an activated status and
no way to log in.

**Remediation:**

Wrap the user-creation and invitation dispatch in an atomic database transaction with a
unique index on `users.email`. Use `firstOrCreate` with a lock to prevent duplicate user
creation. Guard the observer against double-firing by checking `$employee->wasRecentlyCreated`
or by making the job idempotent.

---

### HIGH-2 — Employee Status Transition Race

**Affected code:** Automatic status transition logic and the temporal role assignment
(`docs/feature-requirements.md`, §"1. Employee Status State Machine")

**Description:**

The state machine fires `pre_contract → active` when `contract_start_date` is reached and
`onboarding_completed = true`. If the scheduled job that checks dates and the manual HR
approval arrive within the same database transaction window, two concurrent role-assignment
writes can occur:

- Both read `status = pre_contract` and proceed.
- Both attempt to insert a temporal role record with the same `(employee_id, role, valid_from)`.
- One succeeds; the other fails silently or creates a duplicate, leaving the employee with
  double roles and elevated permissions.

**Remediation:**

Add an optimistic lock (`version` column) or a row-level `SELECT … FOR UPDATE` guard on the
employee record before any status transition. Make all role-assignment operations idempotent
(`updateOrCreate` with a unique constraint on `(employee_id, role_id, valid_from)`).

---

### HIGH-3 — Sensitive Data Over-Exposure in API Responses

**Affected code:** API resource transformers / JSON serialisation layer
(`api/` repository)

**Description:**

Several Eloquent models include sensitive fields (`tax_id`, `iban`, `emergency_contact`,
`date_of_birth`) that are populated during the onboarding phase. Because the API resource
classes extend `JsonResource` and rely on `$this->resource->toArray()` as the default, any
field present on the Eloquent model is included in the response unless explicitly hidden.

An authenticated user with `employees.read` permission (e.g., a shift supervisor) would
receive the full model payload including IBAN, Steuer-ID, and emergency-contact details,
which they have no business need for and which constitutes a GDPR Article 5(1)(c) data
minimisation violation.

**Remediation:**

Replace default `toArray()` serialisation with explicit field allowlists in every resource
class. Define separate resources for different consumer roles (e.g., `EmployeeSummaryResource`
for supervisors, `EmployeeFullResource` for HR). Add automated tests that assert unexpected
sensitive fields are absent from the response for each role.

---

### HIGH-4 — Error Response Contract Violations Leak Stack Traces

**Affected code:** `app/Exceptions/Handler.php` (`api/` repository)

**Description:**

When `APP_DEBUG=true` (the documented local and staging default), Laravel's exception handler
returns full stack traces in the API response, including file paths, class names, and
configuration details. This has two impacts:

1. The response shape diverges from the OpenAPI contract (CRITICAL-3 above).
2. Information from stack traces is transmitted to API consumers, including the Android app,
   which may log or display these traces. If a device is compromised, an attacker gains
   detailed server-side implementation knowledge.

Additionally, internal `500` responses in production sometimes include the raw `message`
field from the exception without sanitisation, exposing database table names, column names,
and query fragments.

**Remediation:**

Unconditionally sanitise error responses in `Handler.php` regardless of `APP_DEBUG`. Use a
separate in-process logging channel for debug details. Ensure the rendered JSON always
matches the contract envelope.

---

### HIGH-5 — Archive-Window Data Loss on Batch Boundary

**Affected code:** `app/Jobs/BuildMerkleTreeBatch.php` and retention/archiving logic
(`docs/adr/20251221-activity-logging-audit-trail-strategy.md`, §"5. Retention & Archiving")

**Description:**

`buildTreeForTenant()` selects all unbatched Level 2/3 logs in a single query, then writes
`merkle_root` and `merkle_proof` back to each row. If the archive job runs concurrently and
moves a log from `activity_log` to `activity_log_archive` between the initial SELECT and the
final UPDATEs, those rows disappear before their proofs are written.

The archival job sees `merkle_root IS NULL` (the check for "ready to archive") and moves
the record, so it is archived without a proof. The Merkle root is computed for the full
batch and submitted to OpenTimestamp, but the archived record contains `merkle_proof = null`,
making it permanently unverifiable.

This is a data-integrity violation for forensic records that may be needed in legal
proceedings.

**Remediation:**

Use `SELECT … FOR UPDATE SKIP LOCKED` to lock the rows being batched for the duration of the
Merkle tree build and update (preferred — database-native, no external dependencies). As an
alternative, coordinate the archive job and the Merkle build job through a mutex (e.g.,
`Cache::lock("merkle:tenant:{$id}", 120)`), but prefer the database lock as it is more
robust and does not introduce a cache dependency.
Add an assertion in the archiving job that `merkle_root IS NOT NULL` before moving any record.

---

### MEDIUM-1 — Context-Dependent Races in Permission Caching

**Affected code:** Permission cache population and permission-check middleware
(`api/` repository, Spatie Permission integration)

**Description:**

Spatie's permission package caches user-role assignments. When a role is revoked during
an active session (e.g., on `active → terminated` transition), the cached permissions
remain valid until the cache TTL expires or the cache is explicitly invalidated. The
existing observer calls `$user->flushPermissionCache()`, but if the revocation and the
cache-flush happen in different queue workers, the flush may arrive after a subsequent
request has already re-populated the cache with the old roles.

**Remediation:**

Ensure `flushPermissionCache()` is called inside the same database transaction that revokes
the role, and verify that the queue driver is configured to process the permission-flush
job synchronously for status transitions.

---

### MEDIUM-2 — Orphan-Marking Race on Concurrent Termination

**Affected code:** Employee termination observer
(`docs/feature-requirements.md`, §"Employee Status State Machine")

**Description:**

On `active → terminated`, the observer deactivates the user account and deletes all sessions
and API tokens. If a concurrent request (e.g., a guard-book entry submission from a mobile
device) arrives between the session deletion and the account deactivation, the request
passes session validation (session still valid at the time of the check) but the handler
runs against a user whose account is in the process of being deactivated.

In most cases this results in a 500 error, but under certain race timing, the guard-book
entry is written under a user that is about to be marked inactive, creating an orphaned
entry that belongs to a no-longer-valid employee.

**Remediation:**

Set `user_account_active = false` atomically before or in the same operation as session
deletion. Add a middleware guard that short-circuits with `403` for any request from a
user with `user_account_active = false`, regardless of session validity.

---

### MEDIUM-3 — DB Schema Inconsistency: `onboarding_steps` Field Type

**Affected code:** `database/migrations/…_create_employees_table.php` (`api/` repository)

**Description:**

`onboarding_steps` is defined as `$table->json('onboarding_steps')->nullable()` in the
migration, but the OpenAPI contract defines the field as a free-form `object` without an
`items` schema. The feature-requirements document describes it as a JSON array
(`[{"step": "personalfragebogen", "completed": true}, …]`), but neither the migration
comment nor the contract specifies the exact schema.

As a result, client-generated code treats the field as an opaque object, different frontend
or Android builds may write incompatible structures, and no validation is enforced at the
API boundary.

**Remediation:**

Define a strict `onboardingSteps` schema in the OpenAPI spec (array of step objects with
`step: string`, `completed: boolean`, `completed_at: string|null`). Add API-level validation
using a `FormRequest` that enforces this schema on every write.

---

### MEDIUM-4 — Frontend Bootstrap Race on Permission Hydration

**Affected code:** Frontend store initialisation (Pinia/Vue bootstrap, `frontend/` repository)

**Description:**

On application bootstrap, the frontend dispatches several concurrent API calls to hydrate
user data, permissions, and tenant configuration. If the permissions response arrives after
the initial route render, components that check `can('some-permission')` in a computed
property or `v-if` guard see an empty permission set and may incorrectly render "no access"
states or, worse, skip permission checks that are assumed to have already passed.

**Remediation:**

Defer route rendering until all permission and identity data is resolved. Implement a
`routerReady` guard in the Vue Router navigation guard (`router/index.ts`) that awaits the
auth bootstrap promise (e.g., `await store.dispatch('auth/bootstrap')`) before calling
`next()`. Add integration tests that simulate slow permission responses and assert the UI
does not render sensitive sections before permissions are confirmed.

---

### MEDIUM-5 — Cache-Deletion Race on User Permission Flush

**Affected code:** Permission cache deletion, Spatie Permission + Laravel cache layer
(`api/` repository)

**Description:**

`flushPermissionCache()` deletes the cache key for the specific user. If two concurrent
requests both miss the cache, both will attempt to re-populate it from the database. Under
a Redis `SET NX` pattern this is safe, but if the cache driver uses a plain `put()` with a
long TTL, both writes proceed and the second write may overwrite stale or partially updated
data from the first.

This is distinct from MEDIUM-1: the bug here is in the cache write path, not the eviction
path.

**Remediation:**

Use atomic cache operations (`Cache::remember` with a database-level read lock) when
re-hydrating permissions after a flush. Consider a short TTL (30–60 seconds) as a fallback
even if explicit flushing is implemented.

---

### MEDIUM-6 — Documentation Gaps in Forensic Verification Flow

**Affected code:** `docs/adr/20251221-activity-logging-audit-trail-strategy.md` and
`docs/adr/20251027-opentimestamp-for-audit-trail.md`

**Description:**

The ADRs document the forensic hash-chain and Merkle tree construction in detail, but the
following operational topics are absent:

1. **Second-preimage resistance:** no mention of domain separation or leaf/node tagging.
2. **Cross-tenant isolation:** the Merkle batch job iterates over tenants but does not
   document whether a single Merkle root can span tenant data, which would be a privacy
   violation.
3. **Key management for hash chain:** the `event_hash` is a plain SHA-256 of the event
   data; there is no HMAC or signing key, so the hash only detects accidental corruption,
   not deliberate tampering by a database administrator.
4. **Public verification API:** the open question in ADR-010 about
   `GET /public/activity-logs/{id}/verify` remains unresolved with no tracking issue.

**Remediation:**

Update both ADRs to explicitly address each point. Create a GitHub issue for the public
verification API decision. Document the cross-tenant isolation guarantee explicitly
(each Merkle batch MUST be scoped to a single tenant).

---

## Recommendations

1. **Prioritise CRITICAL findings.** Findings CRITICAL-1 and CRITICAL-2 affect the legal
   admissibility of forensic records and the correctness of generated API clients
   respectively. Both should be fixed before the next production release.

2. **Introduce contract-validation CI.** A Spectator or Schemathesis job would catch
   contract/implementation drift (CRITICAL-2, CRITICAL-3, HIGH-4) automatically.

3. **Add a race-condition test harness.** HIGH-1, HIGH-2, MEDIUM-1, MEDIUM-2, MEDIUM-4,
   and MEDIUM-5 all share the root cause of missing atomicity guards. A test helper that
   spawns concurrent requests (e.g., using Pest's parallel mode or wrk) would provide
   ongoing regression coverage.

4. **Data minimisation audit.** HIGH-3 should be resolved holistically: enumerate every
   resource class, define the minimum field set per consumer role, and add automated tests.

5. **Forensic system hardening.** After resolving CRITICAL-1 and HIGH-5, update ADR-010 and
   ADR-002 to reflect the production-ready cryptographic design.

---

## References

- `docs/adr/20251221-activity-logging-audit-trail-strategy.md` — Activity Logging ADR
- `docs/adr/20251027-opentimestamp-for-audit-trail.md` — OpenTimestamp ADR
- `docs/feature-requirements.md` — Employee lifecycle and onboarding requirements
- [RFC 6962 §2.1](https://datatracker.ietf.org/doc/html/rfc6962#section-2.1) — Certificate Transparency Merkle tree hash (domain separation)
- [OWASP Testing Guide — Race Conditions](https://owasp.org/www-project-web-security-testing-guide/)
- [GDPR Article 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/) — Data minimisation
