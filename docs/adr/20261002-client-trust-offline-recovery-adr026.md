<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-026: Client Identity, Endpoint Trust, Offline Authorization, and Recovery

**Status:** Accepted

**Date:** 2026-10-02

**Decision authority:** SecPal Product and Domain Owner

**Partially supersedes:** [ADR-012](20260406-single-app-android-distribution-and-private-provisioning-adr012.md)

**Supersedes:** [ADR-003](20251027-offline-first-architecture.md)

**Decision provenance:** This record accepts the client/trust and recovery
rebaseline authorized under [#842](https://github.com/SecPal/.github/issues/842).
Its date is the architecture record date. Acceptance establishes decision
authority, not implementation, availability, deployment, production readiness,
platform qualification, or compliance.

## Context and authority reconciliation

ADR-012 retained one Android package/signing identity and the same package for
normal, Device Owner, and profile-owner operation after its provisioning surfaces
were retired. ADR-003 remained Proposed and non-binding, with historical PWA,
local CRUD, and synchronization examples requiring revalidation. Neither expresses
the current separation of personal authentication, Work access, endpoint
management, offline authority, and recovery.

This is one coherent architecture contract. It replaces ADR-012's single-package,
single-signing, shared-version-line, and same-package-for-normal-and-DPC assumptions
where they conflict with the USER/WORK model below. ADR-012 still owns compatible
distribution decisions: Play Store, GitHub Releases, Obtainium and direct APK
routes; Play-native updates for Play installs; `apk.secpal.app` for artifacts,
checksums and machine-readable release metadata; Stable/Beta tracks and metadata
paths; `secpal.app/android` as the human-facing landing surface; and the prohibition
on long-lived secrets in public distribution artifacts. These routes do not imply
that every new application identity is published through every channel or that
identities share a release/version line. Release realization remains separate.
Completed Epic #586's provisioning retirement remains effective and is not reopened.

ADR-003 is Superseded as the offline architecture source. Its original Proposed
status, date, body, PWA-first sequencing, IndexedDB/Dexie/Workbox, local-first CRUD,
background sync, and LWW/conflict examples remain historical proposals. None is
made binding by this record. Both predecessors retain their historical bodies;
explicit notices define the surviving authority.

[ADR-014](20260720-tenant-identity-access-model-adr014.md) retains global User,
TenantMembership, explicit access, tenant integrity and identity lifecycle
boundaries, as refined for employment/domain authority by
[ADR-025](20261002-employment-time-absence-compensation-adr025.md).
[ADR-015](20260720-global-identity-key-security-adr015.md) continues to own Global
Identity Key security. Personal and endpoint proof keys, application signing,
Recovery Keys and user recovery are not substitutes for its Global Identity
Root/KEK or tenant encryption authority. Infrastructure/state recovery remains
with [ADR-020](20260824-production-state-recovery-authority-separation-adr020.md).
[ADR-023](20260824-public-self-hosting-private-managed-operations-adr023.md),
current [product positioning](../product-positioning.md) and
[BRAND-0007](BRAND-0007-secpal-product-family-architecture.md) remain unchanged
within their scopes. Client families are trust identities within SecPal, not new
product brands.

## Binding decision

### Separate authorities and client families

`User Identity != Personal Device Identity != Work Endpoint Identity != Session != Endpoint Management != Recovery Authority`.

| Family | Surface              | Architecture role                                                               |
| ------ | -------------------- | ------------------------------------------------------------------------------- |
| USER   | `app.secpal`         | Personal application identity; approved personal device and User authentication |
| USER   | `app.secpal.libre`   | Distinct personal application identity, not a store/channel alias               |
| USER   | Normal Browser / PWA | User access with a separate, lower-assurance trusted-browser lifecycle          |
| WORK   | `io.secpal`          | Work application identity on approved Work endpoints                            |
| WORK   | Work Web             | Work access on approved endpoints where Work assurance is required              |
| WORK   | `io.secpal.dpc`      | Separate Android policy-controller identity and management authority            |

`app.secpal`, `app.secpal.libre`, `io.secpal`, and `io.secpal.dpc` each have a
**separate application identity and signing authority**. They are accepted
architecture identities, not variants of one shared signing identity. Neither
common source nor distribution channel merges them. This decision specifies no
signing-key custody, operational rotation, certificates, Play configuration,
release implementation, or final USER/WORK capability matrix. Application signing
alone establishes neither a concrete device identity nor user permissions.

### Work endpoint identity, assurance, and management

`DPC Management != Endpoint Identity != Endpoint Assignment != User Authorization != Session`.

Work endpoint identity identifies a concrete endpoint through authenticated
cryptographic proof, hardware-bound under the applicable qualification contract.
Server approval, endpoint assignment, management policy, user access assignments,
and session lifecycle are separate decisions with separate revocation effects.
Possession, employment, organizational ownership, assignment to a User or site,
and management status confer no implicit user rights.

| Assurance         | Meaning                                                                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APPROVED_WORK`   | Baseline: the concrete endpoint is cryptographically identified and currently server-approved for Work access under the applicable qualification/attestation contract |
| `MANAGED_PROFILE` | Adds Android profile management/policy authority to approved Work identity                                                                                            |
| `FULLY_MANAGED`   | Adds Android fully managed device/policy authority to approved Work identity                                                                                          |

Device Owner or Profile Owner status and DPC claims do not create SecPal endpoint
identity. Management cannot substitute for authenticated endpoint proof or server
approval. Higher management assurance does not expand user authorization.

Endpoint trust is **not** a claim that the endpoint is malware-free, fully
patched, comprehensively monitored, universally compliant, or EDR-qualified.
Posture is a separate possible future capability. Availability of an OS API,
TPM, Secure Enclave, StrongBox, or attestation feature does not establish
Production Qualification.

Work Web must prove approved endpoint identity where Work assurance is required;
JavaScript or a browser cookie cannot establish that identity. A supported desktop
may use a narrow SecPal Endpoint Authenticator/helper for endpoint proof,
hardware-backed key interaction, and protected local-store unlocking where
required. It is not EMM/MDM, EDR, general inventory, patch management, browser
monitoring, employee surveillance, or permanent generic root/admin control.
Failure to establish required qualifying hardware identity denies that Work
assurance; an exportable software key is not a silent fallback.

### Online authorization and disclosure

Effective protected Work authority is bounded by:

`User Authority ∩ Endpoint Authority ∩ Tenant Scope ∩ Resource / Site Scope ∩ Current Server Policy`.

User proof and endpoint proof are independent inputs. User authority follows
ADR-014/ADR-025's active membership, explicit permission/scope, validity and
revocation rules. Online decisions use current authenticated server authority.
Endpoint authority is server-derived from authenticated cryptographic identity
and maintained policy. A session carries authenticated context; it cannot
replace either authority or create permissions.

Device/site IDs, headers, mode flags, capability claims, JavaScript state, DPC
claims and local metadata are requests or evidence to validate, never endpoint
approval or scope authority by themselves. The server resolves requested targets
within the permitted context; caller claims cannot manufacture trust, change
active Tenant authority, or broaden resource access.

Authorization and data minimization apply to identifiers, counts, search,
autocomplete, relation metadata, previews, attachments, exports, notifications,
indexes, and existence-revealing error behavior, as well as full-record fetches.
Where sensitive business/personal payload disclosure is unnecessary, push carries
only an opaque event/sync indication. Protected data is retrieved only after
current authentication and authorization; push delivery is not access authority.

Trust approval collects only security/trust evidence necessary for the defined
contract. It must not require unnecessary installed-app inventories, browser
history, continuous location, process inventories, file contents, or continuous
employee activity profiles. This is an authorization architecture, not a
surveillance architecture.

### Personal devices, trusted browsers, and sessions

`Personal Device Authority != Work Endpoint Authority`.

Approved personal identities in `app.secpal` and `app.secpal.libre` are bound to
the global User and user-authorized, not tenant-owned. Qualified personal identity
material is hardware-bound where the qualified platform permits, non-exportable,
and non-synchronizable as raw private identity material. An approved personal
app device may act as a SecPal User Authenticator. Even on one physical device,
personal and Work identities retain separate authority and lifecycle.

`Trusted Browser != Hardware-bound Personal Device != Session`.

Normal Browser/PWA trust has a separate lower-assurance lifecycle. A trusted
browser is not an approved hardware-bound personal device or Work endpoint.
Session revocation, browser-trust revocation, personal-device revocation, and
Work-endpoint revocation remain separate actions. A login/session alone does not
approve a device. Temporary offline status or unavailability does not revoke an
approved personal device; actual revocation removes its server-side authority.

### Offline-first and authenticated state

**Offline-first is Accepted as a product and architecture requirement.** It does
not promise every operation offline or accept ADR-003's implementation examples.
Permitted local operations are bounded by the relevant authenticated authority.

- **Online:** use current authenticated server authority.
- **Offline:** use the latest mutually known authenticated authority.

Offline authorization derives from authenticated signed state, not local
caller-controlled flags. It must bind the relevant User, Endpoint, Tenant,
Resource/Site, capability/policy and authority generation/version sufficiently to
prevent transfer or scope expansion. Personal/browser authority must not be
substituted for required Work assurance. Missing or unverifiable required state
fails closed for the protected operation.

Once a newer relevant authorization generation/version is accepted, the endpoint
must not roll back to an older known generation, including through restoration
of copied local state. Qualification must establish the required rollback
resistance; this ADR fixes no implementation. An offline endpoint cannot detect
a newer generation it has never learned.

Already-known validity constraints remain binding offline, including ADR-014's
`[valid_from, valid_until)` access intervals. Their evaluation requires qualified,
rollback-resistant time or elapsed-state evidence; a caller-adjustable wall clock
or restored local state must not extend known authority. If required validity
cannot be established, the protected operation fails closed. This is enforcement
of authenticated known limits, not an artificial timeout for unknown remote
revocation. Exact time sources and platform mechanisms remain qualification work.

A fully offline endpoint cannot know about revocation or policy changes after
its last authenticated server state. This architecture promises **no immediate
remote revocation while fully offline** and introduces no artificial global
timeout to simulate it. Explicit local lock and capability-specific policy
constraints remain separate from that limitation; their timing is not decided
here.

### Reconnect before synchronization

On reconnect, the order is mandatory:

1. Establish endpoint proof.
2. Authenticate current User and endpoint authority.
3. Evaluate current server policy, including applicable tenant/resource scope.
4. Only then permit normal synchronization within the resulting authority.

Pending protected mutations must never be uploaded first and revocation discovered
afterward. If the endpoint is currently revoked, there is no normal upload,
normal download, new Work session, or ordinary sync. Pending offline data is
**quarantined/frozen**, neither blindly synchronized nor automatically destroyed
because of revocation. Disposition/recovery requires a separately specified,
authorized process. No final quarantine UX or pending-data recovery workflow is
accepted here. Current policy must likewise constrain synchronization after user,
membership, scope or capability changes; a historical offline snapshot cannot
force server acceptance of a mutation.

### Local protection and offline user authentication

`Endpoint Authorization != User Authorization != Local Lock != Offline Authorization Snapshot`.

Copying a browser profile, local database, filesystem state, backup, or disk image
to another physical device must not recreate approved Work authority or
automatically decrypt protected Work state. Required identity/key binding and
local protection must uphold that invariant independently of client metadata.
A local unlock alone confers no user permissions or server approval.

Local data must preserve equivalent distinctions to **endpoint-shared** data
within endpoint scope, **user-private** data within the authenticated User's
scope, and **session-only** data that cannot silently become a persistent shared
cache. These are protection semantics, not storage tables. Shared/Dedicated
endpoints must not retain unrelated privileged administrative data as a persistent
local cache merely because a privileged User once accessed it. Data access,
retention and cleanup must respect the applicable class and authenticated scope;
revoked pending data follows the quarantine rule rather than indiscriminate
cleanup.

An approved personal app device may authenticate the User locally to an approved
Shared/Dedicated Work endpoint. The Work endpoint proves endpoint identity; the
personal app device separately proves User identity. Both, with the applicable
signed offline authority, yield effective local authenticated authority. Neither
proof can substitute for the other or exceed the snapshot's scope. Fully offline
transport may use QR↔QR or another local protocol; no wire or transport format is
bound here.

### Personal-device approval and first-device bootstrap

While at least one approved personal device exists, approval of another requires
authorization from an already approved personal device, bound to the exact pending
device/key. Email, password alone, TOTP alone, a browser cookie, support operator,
and Recovery Key must not create a weaker parallel approval path. An unavailable
approved device still counts until actually revoked.

The first device for a **genuinely new global User** is a distinct bootstrap case.
A suitably authorized organizational actor may authorize the exact pending first
device/key through a short-lived, single-use, user-bound, purpose-bound bootstrap
grant. That grant approves the device only; it creates no implicit tenant rights
or Work endpoint approval. After the first approval, ordinary approved-device
rules apply. An existing global User gaining a TenantMembership receives no new
first-device bootstrap because the Tenant is new. Loss of devices for an existing
User follows Device or Identity Recovery, not new-user bootstrap.

### Recovery Key and Device Recovery

The Recovery Key is a **Device-Recovery authority**, not a normal login factor,
Tenant access, Work endpoint approval, or substitute for device-to-device
approval. It is created only after the first approved personal app device exists,
and generated/rotated only from an approved personal app device. It is high
entropy, single-use and generation-controlled; use consumes its authority and
rotation invalidates older generations. The server retains appropriate
verification metadata rather than recoverable plaintext. After presentation it
must not be silently retained as an ordinarily readable secret. This does not
prohibit the User's deliberate secure offline custody of the presented key.

Consumption, invalidation and generation state must remain authoritative across
backup/restore; restoring an older verifier must not resurrect a used, revoked
or rotated Recovery Key. If current state cannot be established after restore,
Recovery Key use is frozen until scoped reconciliation invalidates obsolete
verification metadata. This is a required recovery invariant, consistent with
ADR-020's restore boundaries, not a choice of ledger or storage implementation.

While an approved personal device still exists, the Recovery Key must not offer
an easier path for adding another. Device Recovery applies when the User can
still sufficiently prove global identity but lacks an approved personal device;
the Recovery Key may authorize the exact replacement device in that failure class.
Where no Recovery Key exists, an appropriately authorized **current Tenant recovery
authority** may assist with that exact replacement personal device, provided the
User still sufficiently proves identity. Ordinary Device Recovery does not
require agreement from all Tenants and must not reset global identity through
this narrower authority. An unavailable Recovery Key whose verification metadata
still exists must not strand this failure class: with the same sufficient User
identity proof and scoped current Tenant recovery authorization, invalidate that
unavailable key's generation before authorizing the exact replacement through
the no-key path. This is not generation or rotation of a new Recovery Key by a
Tenant; a new key requires an approved replacement personal app device. None of
these paths is available while an approved personal device still exists. This is
not generic account unlock.

### Global Identity Recovery and scoped execution

`Device Recovery != Identity Recovery`.

Global Identity Recovery applies when the User can no longer sufficiently prove
the global identity itself. For a global User with multiple relevant current
TenantMemberships, **all relevant current Tenant recovery authorities** must
authorize global Identity Recovery. One Tenant must not unilaterally take over
the global identity. Device Recovery's narrower assistance cannot be used to
bypass that requirement. Recovery authority relevance must be evaluated against
current authenticated membership/policy state, not a caller-selected Tenant list
or historical ended memberships.

Identity Recovery explicitly resets/re-establishes lost or compromised authorities.
Before enabling replacement User authenticators, it must atomically invalidate
the prior User authenticator registrations, personal-device approvals,
browser-trust grants, sessions/tokens, Recovery Key verification metadata and
User offline-authorization generations. Restore must not re-enable those retired
authorities; uncertain recovery state remains frozen pending scoped
reconciliation. Separate Work endpoint identities and the ADR-015 Global Identity
Key boundary are not implicitly replaced or granted by this reset. A fully
offline endpoint cannot learn the new generation until authenticated reconnection,
so this reset makes no immediate offline-revocation promise. Credentials/keys
are replaced or re-registered, never recovered in plaintext.
Recovery authorization is rights/capability based and bounded to the exact
**actor + action + target + request + device**. No global ADMIN, SUPERADMIN,
RECOVERY_ADMIN, unrestricted support takeover or equivalent policy bypass is
introduced. Recovery grants no implicit functional access or Work approval.

Future execution surfaces may distinguish SecPal Managed out-of-band
recovery authorization/execution and self-hosted local administrative tooling,
consistent with ADR-023. Neither may provide an insecure universal fallback or
bypass this authority model. Recovery restores the normal secure authority path:

`Recovery != Disable Enforcement != Generic Fallback Login != Superuser`.

## Consequences and deliberately open details

Separate identities and lifecycles prevent management, session possession,
distribution and recovery from silently expanding access. Signed offline state
supports useful disconnected work with truthful limits. Reauthorization and
quarantine protect server integrity without treating pending work as disposable.
They require separately tested implementations and platform qualification.

This record binds invariants, not exact DPoP construction or proof headers,
COSE/CWT/CBOR structure, new cryptographic algorithms, helper/browser IPC,
loopback versus other local channels, platform attestation adapters, Secure
Enclave/TPM/StrongBox handling, VM/vTPM qualification, local-lock timing or UX,
quarantine UX or detailed pending-data recovery, DPC provisioning payloads,
Android Enterprise restrictions, recovery CLI or Managed executor, storage
schemas, synchronization/conflict algorithms, or the final capability matrix.
Existing cryptographic decisions inside ADR-015 remain binding within its scope.

No Android, browser, frontend, desktop-helper, DPC, API, recovery, signing-key,
deployment or runtime implementation, package publication, or platform
qualification is performed by this architecture delivery. Android #690/#691
consume this authority separately; neither is absorbed here.

## Alternatives considered

1. **Keep one application/signing identity across USER, WORK and DPC.** Rejected:
   it collapses the accepted client-family and policy-controller boundaries.
2. **Keep offline authority dependent on Proposed ADR-003 or accept its examples.**
   Rejected: a product requirement needs accepted trust semantics without freezing
   unvalidated storage, sync, or conflict implementations.
3. **Use a global offline timeout as remote revocation or sync before checking.**
   Rejected: neither proves current offline authority; uploading before
   reauthorization violates the server trust boundary.
4. **Rewrite historical ADR bodies or split this model among overlapping ADRs.**
   Rejected: explicit supersession preserves history and one current owner for
   this coherent architecture contract.
5. **Provide support/superadmin takeover or one-Tenant global recovery.** Rejected:
   it bypasses scoped recovery and global identity separation.

## Related

- [Issue #842](https://github.com/SecPal/.github/issues/842): delivery authority.
- [ADR index](README.md): current status and predecessor history.
- [Public status semantics](../public-status-semantics.md): accepted architecture
  is not proof of implemented or qualified capability.
- [Android #690](https://github.com/SecPal/android/issues/690) and
  [#691](https://github.com/SecPal/android/issues/691): separately owned consumers.
