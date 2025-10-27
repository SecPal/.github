<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-001: Event Sourcing for Guard Book Entries

**Status:** Proposed

**Date:** 2025-10-27

**Deciders:** @kevalyq

## Context

SecPal requires a **digital guard book** ("Wachbuch") for security service operations. Legal requirements demand:

- **Complete auditability** of all entries
- **Non-repudiation** (Nachweisbarkeit)
- **Tamper-proof** storage
- **Reconstruct historical states** for legal disputes
- **Long-term archival** (potentially 10+ years)

Traditional CRUD operations with database updates/deletes conflict with these requirements, as they destroy historical information.

### Legal Background

German security service regulations (Bewachungsverordnung §7-9) require:

- Written documentation of all incidents and patrols
- Chronological, unchangeable entries
- Signature requirements for shift handovers
- Retention period of at least 2 years (§10)

### Technical Requirements

- Append-only storage (no updates/deletes)
- Cryptographic integrity verification
- Event chaining (blockchain-like)
- Ability to replay history
- Fast read access for current state
- Export capability for legal evidence

## Decision

We will use **Event Sourcing** with **CQRS** (Command Query Responsibility Segregation) for guard book functionality:

### Architecture

```
Write Side (Commands)          Read Side (Queries)
┌─────────────────┐           ┌─────────────────┐
│  User Action    │           │  Read Requests  │
└────────┬────────┘           └────────▲────────┘
         │                             │
         v                             │
┌─────────────────┐                    │
│  Event Store    │                    │
│ (append-only)   │────────────────────┘
│                 │        Projections
│ - PostgreSQL    │
│ - Checksum      │
│ - Chaining      │
└─────────────────┘
```

### Implementation Components

1. **Event Store Table** (`guard_book_events`):
   - Stores ALL changes as immutable events
   - SHA-256 checksum per event
   - Chain linking (previous_event_id)
   - PostgreSQL Row-Level Security (RLS) for append-only enforcement

2. **Projection Tables** (e.g., `guard_book_entries`):
   - Materialized views for fast queries
   - Built from event stream
   - Can be rebuilt anytime via event replay
   - Allows soft deletes (events remain!)

3. **Event Store Service**:
   - `appendEvent()` - Write new events
   - `verifyIntegrity()` - Check chain integrity
   - `replayEvents()` - Rebuild projections

4. **PostgreSQL Features**:
   - Row-Level Security (RLS) policies for append-only
   - JSONB for flexible event payloads
   - Temporal Tables (PostgreSQL 17+) for automatic versioning

## Consequences

### Positive

✅ **Legal compliance:**

- Complete audit trail
- Tamper-proof through checksums + chaining
- Can prove integrity in court

✅ **Technical benefits:**

- Time travel queries (reconstruct any past state)
- Event replay for debugging
- Natural fit for event-driven architecture
- Scalability (separate read/write concerns)

✅ **Business value:**

- Export to PDF with complete history
- Integration with external audit systems
- Digital signatures on events (future)
- Analytics on historical patterns

### Negative

❌ **Complexity:**

- Higher learning curve for developers
- More code to maintain (events + projections)
- Requires discipline (all writes via events)

❌ **Storage:**

- More database space (events + projections)
- Need archival strategy for old events

❌ **Performance:**

- Event replay can be slow for large aggregates
- Need caching/snapshots for performance

## Alternatives Considered

### 1. Traditional CRUD with Audit Log

```php
// Standard Laravel Eloquent
GuardBookEntry::create([...]);
GuardBookEntry::find($id)->update([...]);  // ❌ Overwrites data!

// Separate audit_logs table
AuditLog::create(['action' => 'update', 'old' => ..., 'new' => ...]);
```

**Pros:**

- Simple, well-understood
- Laravel/Eloquent native
- Less code

**Cons:**

- ❌ Audit log is separate (can drift from main data)
- ❌ No integrity guarantees (audit log can be tampered)
- ❌ Can't reconstruct exact historical states
- ❌ Legal uncertainty

### 2. Database Temporal Tables Only

```sql
CREATE TABLE guard_shifts (
    id UUID,
    started_at TIMESTAMPTZ,
    PERIOD FOR system_time
) WITH SYSTEM VERSIONING;
```

**Pros:**

- PostgreSQL built-in feature
- Automatic versioning
- Less application code

**Cons:**

- ❌ PostgreSQL 17+ only (not widely deployed yet)
- ❌ No integrity checksums
- ❌ No event chaining
- ❌ Vendor lock-in (PostgreSQL-specific)
- ℹ️ Can be used **complementary** to event sourcing

### 3. Blockchain (Ethereum/Hyperledger)

**Pros:**

- Maximum tamper-proof guarantees
- Distributed consensus

**Cons:**

- ❌ Massive overkill for single organization
- ❌ High costs (gas fees for Ethereum)
- ❌ Complexity
- ❌ GDPR issues (right to erasure vs. immutability)
- ❌ Performance limitations

**Decision:** Real blockchain is overkill. We use blockchain-like **chaining** (previous_event_id + checksum) without distributed consensus.

### 4. Hybrid: CRUD + Snapshot Events

Only store snapshots at certain intervals (e.g., shift end).

**Pros:**

- Simpler than full event sourcing
- Less storage

**Cons:**

- ❌ Loses granularity between snapshots
- ❌ Legal requirement: **every entry** must be traceable
- ❌ Not a real audit trail

## Implementation Plan

### Phase 1: Foundation (MVP)

- [ ] Create `guard_book_events` migration
- [ ] Implement `GuardBookEventStore` service
- [ ] PostgreSQL RLS policies (append-only)
- [ ] Basic integrity verification

### Phase 2: Core Aggregates

- [ ] `GuardShift` aggregate (shift start/end)
- [ ] `GuardBookEntry` aggregate (incidents, patrols)
- [ ] Event handlers for projections
- [ ] Basic read models

### Phase 3: Legal Features

- [ ] Digital signatures for shift handovers
- [ ] PDF export with full event history
- [ ] Timestamp service integration (RFC 3161)
- [ ] Long-term archival strategy

### Phase 4: Advanced Features

- [ ] Snapshots for performance
- [ ] Event replay UI for admins
- [ ] Analytics on event patterns
- [ ] Integration with external audit systems

## Migration Strategy

For existing data (if any):

1. Create initial "migration" events from current state
2. Mark with special event type: `system.migrated_from_legacy`
3. Include original timestamps in event metadata
4. Document migration in event payload

For development:

- ✅ Start with event sourcing from day one
- No migration needed (greenfield)

## Monitoring & Alerting

Required monitoring:

- Event store growth rate
- Integrity check failures (🚨 critical alert!)
- Event replay performance
- Projection lag (event → read model delay)

## Related

- Issue: _To be created: "Implement Event Sourcing Architecture"_
- ADR-002: Offline-First Architecture (to be written)
- ADR-003: OpenTimestamp Integration (to be written)
- Future ADR: Digital Signature Strategy
- Future ADR: Long-term Archival & WORM Storage
- Reference: [Martin Fowler - Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- Reference: [Greg Young - Event Store](https://www.eventstore.com/blog/what-is-event-sourcing)
- Reference: [OpenTimestamp](https://opentimestamps.org/)

## Open Questions

- [ ] Retention policy for archived events (after legal 2-year minimum)?
- [ ] Snapshot strategy (when aggregate exceeds N events)?
- [ ] Multi-tenancy: Separate event stores per organization?
- [ ] GDPR: How to handle "right to erasure" with immutable events? (Crypto-shredding?)

## Review Notes

_This ADR is **PROPOSED** and open for discussion. Feedback welcome via GitHub issue or direct comment._

---

**Next Steps:**

1. Create GitHub issue for implementation tracking
2. Prototype basic event store in spike branch
3. Validate with legal requirements document
4. Review with potential future contributors
