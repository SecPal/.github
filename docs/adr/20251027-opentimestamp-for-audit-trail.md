<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# ADR-002: OpenTimestamp for Audit Trail

**Status:** Proposed

**Date:** 2025-10-27

**Deciders:** @kevalyq

## Context

SecPal requires **legally provable timestamps** for guard book entries to ensure:

- **Non-repudiation:** Prove when an entry was created
- **Tamper-proof:** Detect backdating or post-facto modifications
- **Long-term verifiability:** Timestamps must remain valid for years (10+ years archival)
- **Audit compliance:** Meet legal requirements for security service documentation

Traditional timestamp approaches have limitations:

- **Internal timestamps:** Easily manipulated (server clock can be changed)
- **Commercial TSA (RFC 3161):** Recurring costs, vendor dependency, trust requirement
- **Centralized services:** Single point of failure, what if provider shuts down?

### Legal Requirements

German security service regulations (BewachV §10) require:

> "Aufzeichnungen sind mindestens zwei Jahre aufzubewahren und auf Verlangen der zuständigen Behörde vorzulegen."

While not explicitly requiring cryptographic timestamps, best practice for legal disputes demands:

- Provable creation time
- Tamper evidence
- Independent verification

## Decision

We will use **OpenTimestamp** (OTS) to provide cryptographically verifiable, blockchain-anchored timestamps for guard book events.

### What is OpenTimestamp?

OpenTimestamp is an open-source, **decentralized timestamping protocol** that:

1. Creates SHA-256 hash of data (e.g., guard book event)
2. Submits hash to Bitcoin blockchain (via public OTS calendars)
3. Bitcoin block inclusion proves "data existed at block time"
4. Anyone can verify timestamp independently (Bitcoin node + OTS proof file)

### Architecture

```
Guard Book Event
      ↓
[1] Calculate SHA-256 hash
      ↓
[2] Submit to OTS Calendar Servers
      ↓
[3] Receive pending OTS proof
      ↓
[4] Wait for Bitcoin block confirmation (~10-60 min)
      ↓
[5] Upgrade proof with Bitcoin attestation
      ↓
[6] Store final OTS proof with event
      ↓
[Later] Verify independently via Bitcoin blockchain
```

### Implementation

**Libraries:**

- **PHP (API):** [`opentimestamps/php-opentimestamps`](https://github.com/opentimestamps/php-opentimestamps)
- **JavaScript (Frontend):** [`opentimestamps/javascript-opentimestamps`](https://github.com/opentimestamps/javascript-opentimestamps)

**Database Schema:**

```php
Schema::table('guard_book_events', function (Blueprint $table) {
    // Existing columns...
    $table->binary('ots_proof')->nullable(); // OpenTimestamp proof file
    $table->timestamp('ots_submitted_at')->nullable();
    $table->timestamp('ots_confirmed_at')->nullable(); // When Bitcoin block confirmed
    $table->string('ots_bitcoin_block_height', 20)->nullable();
});
```

**Workflow:**

1. **Event Creation:**

   ```php
   $event = GuardBookEvent::create([...]);
   $hash = hash('sha256', json_encode($event->toArray()));

   // Submit to OTS (async job)
   dispatch(new SubmitToOpenTimestamp($event, $hash));
   ```

2. **OTS Submission (Background Job):**

   ```php
   class SubmitToOpenTimestamp {
       public function handle() {
           $ots = new OpenTimestamps\Client();
           $proof = $ots->stamp($this->hash);

           $this->event->update([
               'ots_proof' => $proof->serialize(),
               'ots_submitted_at' => now(),
           ]);
       }
   }
   ```

3. **OTS Upgrade (Hourly Cron):**

   ```php
   // Check pending OTS proofs and upgrade when Bitcoin block available
   class UpgradeOpenTimestamps {
       public function handle() {
           $pending = GuardBookEvent::whereNotNull('ots_submitted_at')
                                     ->whereNull('ots_confirmed_at')
                                     ->get();

           foreach ($pending as $event) {
               $proof = OpenTimestamps\Proof::deserialize($event->ots_proof);

               if ($upgraded = $proof->upgrade()) {
                   $event->update([
                       'ots_proof' => $upgraded->serialize(),
                       'ots_confirmed_at' => now(),
                       'ots_bitcoin_block_height' => $upgraded->bitcoinBlockHeight(),
                   ]);
               }
           }
       }
   }
   ```

4. **Verification (Anytime):**

   ```php
   public function verifyTimestamp(GuardBookEvent $event): bool {
       $proof = OpenTimestamps\Proof::deserialize($event->ots_proof);
       $hash = hash('sha256', json_encode($event->toArray()));

       return $proof->verify($hash);
   }
   ```

## Consequences

### Positive

✅ **Zero cost:**

- No recurring TSA fees
- Free public OTS calendar servers
- Bitcoin network fees paid by OTS operators

✅ **Decentralized:**

- No vendor lock-in
- No trust in single authority
- Bitcoin blockchain as trust anchor

✅ **Long-term verifiability:**

- Bitcoin blockchain persists (incentive aligned)
- Proof files are standalone (no external service needed for verification)
- Works even if OTS project shuts down

✅ **Legal validity:**

- Cryptographically proven timestamp
- Independently verifiable by courts/auditors
- No reliance on "trusted third party"

✅ **Tamper-proof:**

- Changing event data invalidates hash
- Bitcoin block inclusion is immutable
- Backdating is cryptographically impossible

### Negative

❌ **Delayed confirmation:**

- Initial proof is "pending" (not Bitcoin-backed)
- Full proof requires Bitcoin block (~10-60 minutes)
- Not instant (unlike centralized TSA)

**Mitigation:**

- Store internal timestamp (`created_at`) for immediate ordering
- OTS proof is added asynchronously
- For legal disputes, final OTS proof is authoritative

❌ **Complexity:**

- Requires Bitcoin understanding
- More complex than "call TSA API"
- Need background jobs for upgrade process

❌ **Dependency on Bitcoin:**

- Assumes Bitcoin blockchain remains available
- If Bitcoin network fails, no new timestamps (but existing remain valid!)

❌ **Legal uncertainty:**

- Not a "qualified timestamp" under eIDAS
- German courts may not be familiar with OTS
- May require expert witness to explain

**Mitigation:**

- Document clearly in legal review (Issue #46)
- Provide verification guide for courts
- Consider complementary approach (internal + OTS)

## Alternatives Considered

### 1. RFC 3161 Timestamp Authority (TSA)

**Example providers:**

- D-Trust (German)
- SwissSign (Swiss)
- Sectigo (International)

**Pros:**

- eIDAS qualified timestamps (legal certainty)
- Instant confirmation
- Well-understood by courts

**Cons:**

- ❌ Recurring costs (€0.01-0.10 per timestamp)
- ❌ Vendor dependency (what if provider shuts down?)
- ❌ Trust requirement (must trust TSA)
- ❌ At scale (1000 events/day): €3,650-36,500/year!

### 2. Internal Timestamps Only

Just use `created_at` from database.

**Pros:**

- Free
- Simple
- Instant

**Cons:**

- ❌ Zero legal value (server clock can be changed)
- ❌ No tamper evidence
- ❌ Not suitable for legal disputes

### 3. Hybrid: Internal + OTS

Use both internal timestamps AND OpenTimestamp.

**Pros:**

- ✅ Best of both worlds
- ✅ Immediate ordering (internal)
- ✅ Legal proof (OTS)

**Cons:**

- Slightly more complex

**Decision:** This is actually our chosen approach! Internal `created_at` + async OTS proof.

### 4. Private Blockchain (Hyperledger, Ethereum)

**Pros:**

- More control
- Potentially faster

**Cons:**

- ❌ Must run own nodes
- ❌ Less trustworthy than Bitcoin (smaller network)
- ❌ Infrastructure costs
- ❌ Complexity

### 5. Merkle Tree + Daily Bitcoin Anchoring

Batch events into Merkle tree, anchor root daily.

**Pros:**

- Lower Bitcoin transaction frequency
- Still decentralized

**Cons:**

- ❌ Delayed timestamps (up to 24h)
- ❌ More complex implementation
- ℹ️ This is essentially what OTS calendars do!

## Implementation Plan

### Phase 1: Basic OTS Integration

- [ ] Add `ots_proof`, `ots_submitted_at`, `ots_confirmed_at` columns
- [ ] Install PHP OpenTimestamp library
- [ ] Implement `SubmitToOpenTimestamp` job
- [ ] Test with single event

### Phase 2: Automated Workflow

- [ ] Background job for OTS submission
- [ ] Hourly cron for proof upgrade
- [ ] Monitoring/alerts for failed timestamps

### Phase 3: Verification & Export

- [ ] Verification endpoint: `GET /v1/events/{id}/verify-timestamp`
- [ ] PDF export includes OTS proof
- [ ] Standalone verification tool for auditors

### Phase 4: Documentation

- [ ] Legal guide: "How to verify SecPal timestamps in court"
- [ ] Technical documentation for auditors
- [ ] API documentation for timestamp endpoints

## OpenTimestamp Specifics

### Public Calendar Servers

OTS uses multiple public calendars (free, run by community):

- `https://alice.btc.calendar.opentimestamps.org`
- `https://bob.btc.calendar.opentimestamps.org`
- `https://finney.calendar.eternitywall.com`

**Redundancy:** Submit to all, use first confirmed proof.

### Bitcoin Block Time

Average: ~10 minutes
Variance: 1-60 minutes (rare outliers)

**For SecPal:** This is acceptable. Legal disputes happen months/years later, not minutes after event.

### Storage Requirements

- OTS proof file: ~1-5 KB per event
- For 10,000 events: ~10-50 MB
- Negligible compared to event JSON payload

### Verification Process (For Courts/Auditors)

```bash
# 1. Install OTS client
pip install opentimestamps-client

# 2. Verify proof
ots verify event-12345.ots event-12345.json

# Output:
# Success! Bitcoin block 750123 attests existence as of 2025-10-27 14:23:45 UTC
```

## Security Considerations

### What We're Proving

✅ **Data existed at time T:** If event E is in Bitcoin block B, then E existed at block B's timestamp
✅ **Tamper detection:** Changing E invalidates hash, proof no longer matches

### What We're NOT Proving

❌ **Content correctness:** Doesn't prove event data is truthful, only that it existed
❌ **Author identity:** Doesn't prove who created the event (use digital signatures for that)
❌ **Deletion:** Doesn't prevent deletion (but proves deletion happened after timestamp)

### Complementary Measures

- **Event chaining** (ADR-001): Prevents reordering/insertion
- **Digital signatures:** Proves author identity
- **Append-only database:** Prevents updates/deletes

**Together:** Comprehensive audit trail!

## GDPR Considerations

**Question:** Does Bitcoin-anchored timestamp conflict with "right to erasure"?

**Answer:** No, because:

1. OTS only stores **hash** (not personal data)
2. Hash is pseudonymized (can't reverse to personal data)
3. Legal retention (BewachV §10: 2 years) overrides GDPR erasure for business records

## Cost Analysis

**Traditional TSA (RFC 3161):**

- 1,000 events/day × €0.05 = €50/day = €18,250/year
- 10,000 events/day = €182,500/year

**OpenTimestamp:**

- €0/year (free)
- Infrastructure: Background job scheduler (already needed for other tasks)

**ROI:** Immediate! No-brainer for cost-conscious startups.

## Legal Review Required

**Before production use, confirm with lawyer:**

- [ ] Is OpenTimestamp legally acceptable in German courts?
- [ ] Does it satisfy BewachV §10 retention requirements?
- [ ] Is it sufficient for DIN 77200 compliance?
- [ ] Should we complement with qualified timestamps (eIDAS) for critical events?
- [ ] How to present OTS verification in court proceedings?

## Monitoring & Alerting

**Required monitoring:**

- 🚨 **Critical:** OTS submission failures (retry logic!)
- ⚠️ **Warning:** Proof upgrade taking >2 hours (Bitcoin network congestion?)
- ℹ️ **Info:** Daily count of timestamped events

**Metrics:**

- OTS confirmation latency (time from submission to Bitcoin block)
- Proof upgrade success rate
- Failed timestamp count

## Related

- ADR-001: Event Sourcing for Guard Book
- Future ADR: Digital Signature Strategy
- Issue #46: Legal Review of CLA and Commercial Licenses
- Reference: [OpenTimestamp Whitepaper](https://petertodd.org/2016/opentimestamps-announcement)
- Reference: [Bitcoin Timestamp Security](https://eprint.iacr.org/2021/419.pdf)

## Open Questions

- [ ] Do we timestamp EVERY event, or only critical ones (shift end, incident reports)?
- [ ] Should we run our own OTS calendar server for redundancy?
- [ ] How to handle Bitcoin network downtime (rare but possible)?
- [ ] Should we provide OpenTimestamp verification UI in frontend?

## Next Steps

1. **Legal consultation:** Confirm OTS acceptability with lawyer (Issue #46)
2. **Prototype:** Test OTS integration with sample events
3. **Performance test:** Benchmark OTS submission/upgrade at scale
4. **Documentation:** Write verification guide for non-technical auditors
5. **Implement:** Phase 1 after legal clearance

---

**Note:** This ADR assumes OpenTimestamp is legally sufficient. If legal review determines otherwise, we may need to complement with qualified timestamps (eIDAS) for critical events, while still using OTS for cost-effective bulk timestamping.
