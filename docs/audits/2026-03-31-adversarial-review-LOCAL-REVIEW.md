<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Local Review — 2026-03-31 Adversarial Security Audit

**Document reviewed:** `docs/audits/2026-03-31-adversarial-review.md`
**Review date:** 2026-03-31
**Reviewer:** Internal security team (4-pass local review, per SecPal governance standard)
**Outcome:** Zero blocking issues identified; minor clarifications applied inline.

---

## Pass 1 — Comprehensive Review

_Correctness, completeness, test coverage, documentation, stray TODOs_

| Item | Status | Notes |
| ---- | ------ | ----- |
| All 14 findings documented with severity, affected code, description, attack scenario, and remediation | ✅ | |
| Findings reference actual code paths described in existing ADRs | ✅ | |
| Severity classifications are consistent with CVSS intent (CRITICAL = direct legal/forensic impact; HIGH = exploitable in normal operation; MEDIUM = race/edge-case) | ✅ | |
| Recommendations section synthesises cross-cutting themes | ✅ | |
| References section cites primary sources | ✅ | |
| No stray TODO, FIXME, or placeholder text | ✅ | |
| SPDX header present and correct | ✅ | CC0-1.0 appropriate for documentation |

**Pass 1 verdict: Approved**

---

## Pass 2 — Deep-Dive Review

_Domain policy, licensing, security-sensitive patterns_

| Item | Status | Notes |
| ---- | ------ | ----- |
| CRITICAL-1 second-preimage attack description is technically accurate | ✅ | RFC 6962 §2.1 domain separation correctly cited |
| Code snippets in CRITICAL-1 use correct PHP syntax for hex-string to binary conversion (`hex2bin`) | ✅ | |
| CRITICAL-2 UUID vs. integer finding correctly identifies the source of truth as the API migration | ✅ | |
| CRITICAL-3 error response shape finding cites a real Laravel behaviour (`Handler.php` + `APP_DEBUG`) | ✅ | |
| HIGH-1 TOCTOU description correctly identifies the gap between user creation and invitation dispatch | ✅ | |
| HIGH-2 status transition race correctly identifies the lack of a row-level lock | ✅ | |
| HIGH-3 data minimisation finding correctly cites GDPR Article 5(1)(c) | ✅ | |
| HIGH-5 archive-window finding correctly identifies the SELECT → UPDATE gap in `BuildMerkleTreeBatch` | ✅ | `FOR UPDATE SKIP LOCKED` recommendation is correct for MySQL/MariaDB |
| No domain-policy violations in examples (all examples use `secpal.dev` or redacted paths) | ✅ | |
| No secrets, credentials, or real tenant data included | ✅ | |
| All code examples are illustrative (not production-ready) and labelled as such by context | ✅ | |

**Pass 2 verdict: Approved**

---

## Pass 3 — Best-Practices Review

_Hidden files, governance docs, package metadata, workflow hygiene_

| Item | Status | Notes |
| ---- | ------ | ----- |
| Document follows existing `docs/` Markdown conventions (HTML SPDX comment header, ATX headings) | ✅ | |
| File is placed in the new `docs/audits/` sub-directory, consistent with ADR placement in `docs/adr/` | ✅ | |
| Filename follows date-prefixed kebab-case convention (matches ADR naming) | ✅ | |
| `CHANGELOG.md` updated with a corresponding entry | ✅ | Entry added under 2026-03-31 |
| No binary files, build artifacts, or dependency files introduced | ✅ | |
| Cross-references to ADRs use relative paths | ✅ | |

**Pass 3 verdict: Approved**

---

## Pass 4 — Security Review

_Explicit permissions, secret handling, ignore rules, automation safety_

| Item | Status | Notes |
| ---- | ------ | ----- |
| Document does not contain exploitable attack scripts or weaponised proof-of-concept code | ✅ | Attack scenarios are descriptive, not executable |
| Findings do not reveal undisclosed production credentials, API tokens, or private endpoints | ✅ | |
| Remediation guidance does not introduce new attack surface (e.g., no `eval`, no unsafe deserialisers) | ✅ | |
| All code snippets follow the principle of least privilege in their remediations | ✅ | |
| No finding is suppressed without documented rationale | ✅ | All 14 findings are fully recorded |
| Sensitive field names (IBAN, Steuer-ID, emergency_contact) mentioned in HIGH-3 are generic and already documented in feature requirements | ✅ | Not new disclosures |

**Pass 4 verdict: Approved**

---

## Overall Verdict

**All four passes: APPROVED — zero blocking issues.**

The document is ready to be committed to the repository. Remediation tracking issues should
be opened in the relevant repositories (`api/`, `frontend/`, `contracts/`) referencing this
document once it is merged.
