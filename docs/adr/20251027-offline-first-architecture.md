<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-003: Offline-First Architecture

**Status:** Proposed

**Date:** 2025-10-27

**Deciders:** @kevalyq

> **Current-architecture revalidation notice (2026-08-24):** This remains a
> Proposed, non-binding response to the offline-connectivity problem. PWA-first
> sequencing, “native apps later if needed”, IndexedDB/Dexie/Workbox examples,
> and conflict details such as LWW are historical examples rather than current
> architecture. SecPal now has web/PWA and native-shell client surfaces; that is
> current evidence only, not acceptance of an offline synchronization design.

## Context

Security guards work in environments with **unreliable or no internet connectivity:**

- **Basements, underground parking:** No cell signal
- **Remote locations:** Industrial areas, construction sites
- **Elevator shafts, stairwells:** Signal loss
- **Budget constraints:** Guards may use WiFi-only devices (no data plan)

Guards must be able to:

- ✅ Record incidents immediately (can't wait for connectivity)
- ✅ Complete shift handovers without internet
- ✅ Scan checkpoints on patrol routes
- ✅ Take photos of incidents
- ✅ View previous entries (recent history)

**Traditional online-only approach fails:**

- ❌ "No connection" error frustrates users
- ❌ Lost data if device dies before sync
- ❌ Poor user experience (waiting for API responses)

## Decision

We will implement an **offline-first architecture** where:

1. **Frontend (React PWA) is the primary data store** while offline
2. **All CRUD operations work locally first** (IndexedDB)
3. **Background sync** pushes changes to API when online
4. **Conflict resolution** handles concurrent edits
5. **API remains source of truth** for long-term storage

### Architecture Patterns

```
┌─────────────────────────────────────────┐
│  React Frontend (PWA)                    │
│  ┌─────────────────────────────────┐   │
│  │  UI Components                   │   │
│  └──────────┬───────────────────────┘   │
│             ↓                             │
│  ┌─────────────────────────────────┐   │
│  │  Local State (Zustand/Redux)    │   │
│  └──────────┬───────────────────────┘   │
│             ↓                             │
│  ┌─────────────────────────────────┐   │
│  │  IndexedDB (Dexie.js)           │   │
│  │  - guard_book_entries (local)   │   │
│  │  - pending_uploads (queue)      │   │
│  │  - last_sync_timestamp          │   │
│  └──────────┬───────────────────────┘   │
│             ↓                             │
│  ┌─────────────────────────────────┐   │
│  │  Sync Manager                    │   │
│  │  - Detects online/offline        │   │
│  │  - Pushes pending changes        │   │
│  │  - Pulls remote updates          │   │
│  │  - Resolves conflicts            │   │
│  └──────────┬───────────────────────┘   │
└─────────────┼───────────────────────────┘
              ↓
       [When Online]
              ↓
   ┌──────────────────────┐
   │  API (Laravel)       │
   │  - Event Store       │
   │  - PostgreSQL        │
   └──────────────────────┘
```

## Implementation Details

### 1. Progressive Web App (PWA)

**Service Worker** for offline capability:

```typescript
// src/service-worker.ts
import { precacheAndRoute } from "workbox-precaching";
import { registerRoute } from "workbox-routing";
import { NetworkFirst, CacheFirst } from "workbox-strategies";

// Cache app shell (HTML, CSS, JS)
precacheAndRoute(self.__WB_MANIFEST);

// API requests: Network first, fallback to cache
registerRoute(
  ({ url }) => url.pathname.startsWith("/api/"),
  new NetworkFirst({
    cacheName: "api-cache",
    networkTimeoutSeconds: 3,
  })
);

// Static assets: Cache first
registerRoute(
  ({ request }) => request.destination === "image",
  new CacheFirst({ cacheName: "images" })
);
```

### 2. Local Database (IndexedDB via Dexie.js)

```typescript
// src/db/schema.ts
import Dexie, { Table } from "dexie";

export interface GuardBookEntry {
  id: string; // UUID (generated locally)
  shiftId: string;
  entryType: "routine" | "incident" | "patrol" | "handover";
  description: string;
  location: { lat: number; lon: number; accuracy: number };
  createdAt: string; // ISO 8601
  syncStatus: "pending" | "synced" | "conflict";
  syncedAt?: string;
  serverId?: string; // ID from API after sync
  photos: Photo[];
}

export class SecPalDB extends Dexie {
  guardBookEntries!: Table<GuardBookEntry, string>;

  constructor() {
    super("SecPalDB");
    this.version(1).stores({
      guardBookEntries: "id, shiftId, createdAt, syncStatus",
    });
  }
}

export const db = new SecPalDB();
```

### 3. Sync Manager

```typescript
// src/sync/SyncManager.ts
import { db, GuardBookEntry } from "@/db/schema";
import { apiClient } from "@/api/client";

export class SyncManager {
  private syncInProgress = false;

  async sync(): Promise<void> {
    if (!navigator.onLine || this.syncInProgress) return;

    this.syncInProgress = true;

    try {
      // 1. Push local changes to server
      await this.pushLocalChanges();

      // 2. Pull remote updates
      await this.pullRemoteUpdates();

      // 3. Mark successful sync
      localStorage.setItem("lastSyncAt", new Date().toISOString());
    } finally {
      this.syncInProgress = false;
    }
  }

  private async pushLocalChanges(): Promise<void> {
    const pending = await db.guardBookEntries.where("syncStatus").equals("pending").toArray();

    for (const entry of pending) {
      try {
        const response = await apiClient.post("/guard-book/entries", {
          shiftId: entry.shiftId,
          entryType: entry.entryType,
          description: entry.description,
          location: entry.location,
          createdAt: entry.createdAt,
          localId: entry.id, // Include for conflict detection
        });

        // Update local entry with server ID
        await db.guardBookEntries.update(entry.id, {
          syncStatus: "synced",
          syncedAt: new Date().toISOString(),
          serverId: response.data.id,
        });
      } catch (error) {
        if (error.response?.status === 409) {
          // Conflict detected
          await db.guardBookEntries.update(entry.id, {
            syncStatus: "conflict",
          });
        }
        // Other errors: retry later (keep as pending)
      }
    }
  }

  private async pullRemoteUpdates(): Promise<void> {
    const lastSync = localStorage.getItem("lastSyncAt");

    const response = await apiClient.get("/guard-book/entries", {
      params: { since: lastSync },
    });

    for (const serverEntry of response.data) {
      // Check if we have this entry locally
      // .first() returns undefined if no entry is found
      const local = await db.guardBookEntries.where("serverId").equals(serverEntry.id).first();

      if (local == null) {
        // New entry from server (created by other device/user)
        await db.guardBookEntries.add({
          id: crypto.randomUUID(),
          serverId: serverEntry.id,
          shiftId: serverEntry.shiftId,
          entryType: serverEntry.entryType,
          description: serverEntry.description,
          location: serverEntry.location,
          createdAt: serverEntry.createdAt,
          syncStatus: "synced",
          syncedAt: new Date().toISOString(),
          photos: serverEntry.photos || [],
        });
      }
    }
  }
}

// Auto-sync when online
export const syncManager = new SyncManager();

window.addEventListener("online", () => {
  syncManager.sync();
});

// Periodic background sync (every 5 minutes when online)
setInterval(
  () => {
    if (navigator.onLine) {
      syncManager.sync();
    }
  },
  5 * 60 * 1000
);
```

### 4. React Hook for Offline-Aware Data

```typescript
// src/hooks/useGuardBookEntries.ts
import { useLiveQuery } from "dexie-react-hooks";
import { db } from "@/db/schema";

export function useGuardBookEntries(shiftId: string) {
  // Dexie-react-hooks provides real-time updates
  const entries = useLiveQuery(
    () => db.guardBookEntries.where("shiftId").equals(shiftId).reverse().sortBy("createdAt"),
    [shiftId]
  );

  const addEntry = async (entry: Omit<GuardBookEntry, "id" | "syncStatus">) => {
    const id = crypto.randomUUID();

    await db.guardBookEntries.add({
      ...entry,
      id,
      syncStatus: "pending",
      createdAt: new Date().toISOString(),
      photos: [],
    });

    // Trigger sync if online
    if (navigator.onLine) {
      syncManager.sync();
    }
  };

  return { entries, addEntry };
}
```

### 5. Conflict Resolution Strategy

**Conflict scenarios:**

1. **Same entry edited offline on 2 devices:** Last-write-wins (LWW) based on `createdAt`
2. **Entry deleted on server, edited locally:** Server wins (deletion prevails)
3. **Network partition:** Queue local changes, merge when reconnected

**Implementation:**

```typescript
enum ConflictResolution {
  SERVER_WINS = "server_wins",
  CLIENT_WINS = "client_wins",
  MANUAL = "manual", // Show UI for user decision
}

interface ConflictHandler {
  resolve(local: GuardBookEntry, remote: GuardBookEntry): ConflictResolution;
}

// Simple LWW strategy
class LastWriteWinsHandler implements ConflictHandler {
  resolve(local: GuardBookEntry, remote: GuardBookEntry): ConflictResolution {
    const localTime = new Date(local.createdAt).getTime();
    const remoteTime = new Date(remote.createdAt).getTime();

    return remoteTime > localTime ? ConflictResolution.SERVER_WINS : ConflictResolution.CLIENT_WINS;
  }
}
```

**For SecPal guard book:**

- Most entries are append-only (incidents, patrol checks)
- Conflicts rare (different guards, different shifts)
- **Strategy:** Last-write-wins is acceptable, with conflict notification

## Consequences

### Positive

✅ **Guards can work anywhere:**

- No frustrating "no connection" errors
- Reliable data capture

✅ **Better UX:**

- Instant response (no API latency)
- App feels native, not "web app"

✅ **Data resilience:**

- No data loss if device dies before sync
- Queued changes persist across app restarts

✅ **Reduced server load:**

- Fewer API requests (batch sync vs. real-time)
- Lower hosting costs

### Negative

❌ **Complexity:**

- Sync logic is non-trivial
- Conflict resolution edge cases
- More testing required (online, offline, flaky network)

❌ **Storage limitations:**

- IndexedDB quotas (browser-dependent, usually 50-100 MB)
- Must prune old data or archive to server

❌ **Debugging challenges:**

- State lives in multiple places (IndexedDB, API, memory)
- Harder to reproduce bugs ("it worked in the office but not in the field")

❌ **Security considerations:**

- Sensitive data in IndexedDB (unencrypted by default)
- Compromised device = data leak

**Mitigation:** Encrypt sensitive data in IndexedDB (Web Crypto API)

## Alternatives Considered

### 1. Online-Only (Traditional SPA)

Every action requires API call.

**Pros:**

- Simple architecture
- No sync complexity

**Cons:**

- ❌ Unusable offline (dealbreaker for guards!)
- ❌ Poor UX (network latency)

**Rejected:** Not viable for field operations.

### 2. Offline-Only (Local App with Manual Export)

Data stays local, manual export to server.

**Pros:**

- No sync complexity
- Always works

**Cons:**

- ❌ No real-time collaboration
- ❌ Manual step (guards forget to sync)
- ❌ No backup (device loss = data loss)

**Rejected:** Too risky for legal compliance.

### 3. CRDTs (Conflict-Free Replicated Data Types)

Use CRDT libraries (Yjs, Automerge) for automatic conflict resolution.

**Pros:**

- Automatic conflict resolution
- Mathematically proven convergence

**Cons:**

- ❌ High complexity
- ❌ Large library size (bundle bloat)
- ❌ Overkill for append-only guard book

**Decision:** Not needed. Most guard book entries are append-only. LWW is sufficient.

### 4. Native Mobile App (React Native)

Build separate iOS/Android apps.

**Pros:**

- Better offline support (SQLite)
- Native performance

**Cons:**

- ❌ Duplication (web + mobile)
- ❌ App store approval delays
- ❌ Higher maintenance burden

**Decision:** PWA first. Native apps later if needed (see `ideas-backlog.md`).

## Technology Choices

### IndexedDB vs. LocalStorage vs. SQLite

| Feature         | IndexedDB | LocalStorage | SQLite (Native)  |
| --------------- | --------- | ------------ | ---------------- |
| Storage size    | ~50-100MB | ~5-10MB      | Unlimited        |
| Async API       | ✅        | ❌           | ✅               |
| Transactions    | ✅        | ❌           | ✅               |
| Indexing        | ✅        | ❌           | ✅               |
| Browser support | ✅        | ✅           | ❌ (native only) |

**Decision:** IndexedDB (via Dexie.js for simpler API)

### Dexie.js vs. idb vs. PouchDB

| Library  | Size   | API Style     | Sync Built-in |
| -------- | ------ | ------------- | ------------- |
| Dexie.js | ~20KB  | Promise-based | ❌            |
| idb      | ~3KB   | Promise-based | ❌            |
| PouchDB  | ~150KB | CouchDB-like  | ✅ (CouchDB)  |

**Decision:** Dexie.js

- Good balance of features vs. size
- Excellent TypeScript support
- Reactive hooks for React (dexie-react-hooks)

### Service Worker Frameworks

**Decision:** Workbox (Google)

- Battle-tested (used by Google apps)
- Good caching strategies
- Vite plugin available

## Mobile-First Design Integration

**Synergy with ADR-004 (Mobile-First Design):**

- Touch-optimized UI works well offline
- Large buttons reduce errors (important when network unavailable)
- Progressive disclosure (only load what's needed = less data to sync)

## Testing Strategy

**Must test scenarios:**

1. **Pure offline:** App starts with no network
2. **Going offline:** Network drops during operation
3. **Coming online:** Network reconnects mid-operation
4. **Flaky network:** Intermittent connectivity (airplane mode on/off)
5. **Conflicting edits:** Same entry edited on 2 devices
6. **Long offline period:** Device offline for days, then syncs

**Tools:**

- Chrome DevTools: Offline simulation
- Playwright: E2E tests with network conditions
- Mock Service Worker (MSW): API mocking

## Monitoring & Observability

**Metrics to track:**

- Offline session duration (how long guards work offline?)
- Sync success rate
- Conflict frequency
- IndexedDB storage usage
- Failed sync attempts

**Alerts:**

- 🚨 Sync failures >10% (backend issue?)
- ⚠️ IndexedDB quota exceeded (prune old data!)

## Legal/Compliance Considerations

**Question:** Is offline data legally valid?

**Answer:** Yes, IF:

- ✅ Offline entry has `createdAt` timestamp (internal clock)
- ✅ OpenTimestamp applied after sync (ADR-002)
- ✅ Event chaining ensures no insertion/reordering (ADR-001)

**Together:** Offline entry + later timestamp = legally defensible.

## Related

- ADR-001: Event Sourcing (ensures no data loss)
- ADR-002: OpenTimestamp (timestamps offline events after sync)
- ADR-004: Mobile-First Design (to be written)
- Future: Native Mobile Apps (if PWA insufficient)

## Open Questions

- [ ] IndexedDB encryption: Web Crypto API or library (simple-crypto-js)?
- [ ] Quota management: Auto-prune entries older than 30 days?
- [ ] Conflict UI: Show banner "Conflict detected, server version used"?
- [ ] Photo handling: Compress before storing in IndexedDB? Upload separately?

## Implementation Plan

### Phase 1: Basic Offline Support

- [ ] Set up Service Worker (Workbox)
- [ ] IndexedDB schema (Dexie.js)
- [ ] Basic CRUD works offline

### Phase 2: Sync Logic

- [ ] Sync manager (push/pull)
- [ ] Conflict detection
- [ ] Online/offline status UI

### Phase 3: Advanced Features

- [ ] Photo upload queue
- [ ] Background sync API (when browser supports)
- [ ] Encrypted IndexedDB

### Phase 4: Testing & Polish

- [ ] E2E tests for offline scenarios
- [ ] Performance optimization (lazy loading)
- [ ] User guide: "How offline mode works"

## Next Steps

1. Prototype PWA with basic offline (spike branch)
2. Test on real devices (Android/iOS, different browsers)
3. User testing with actual guards (field test!)
4. Iterate based on feedback

---

**Status:** Proposed, pending prototype validation.
