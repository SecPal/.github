<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# US-008: Validation evidence and draft PR checklist

This note records validation commands, repository SHAs, live smoke checks, E2E coverage gaps, and **draft PR** expectations for the contract-doc drift cleanup track (US-001 through US-007). Use it when opening or updating draft PRs in each affected repository.

## Before / after drift summary

**Baseline (US-001 snapshot):** See `US-001-evidence-matrix.md`. At that time, OpenAPI lacked qualification catalog, employee nested qualifications, employee-qualification pivot CRUD, employee documents, and verification-resend documentation; summary docs also overstated REST counts and “future” endpoints.

**After US-002–US-007 (this cleanup):**

| Area | Change |
| ---- | ------ |
| OpenAPI | Verified-endpoint presence guard (16 operations); full paths/schemas for verification resend, employee documents, qualification catalog, employee qualifications (nested + pivot). |
| API repo | Feature tests extended (`AuthTest` resend/throttle, `QualificationControllerTest` resource shape); RBAC README/architecture docs corrected (18 ops, no fictitious `/roles/{id}/permissions`). |
| Contracts repo | README reflects real coverage; stubs replaced with request/response schemas aligned to Laravel. |
| **Additional drift still present (document for client work):** Frontend `qualificationApi` / types may still use names like `requires_certificate`, `issued_date`, or `pending` status where the API uses `requires_renewal`, `obtained_date`, and `valid` \| `expiring_soon` \| `expired` — see US-001 matrix “Related drift” rows. OpenAPI and backend tests are authoritative; SPA alignment is **out of scope** for these contract-doc stories unless explicitly scheduled. |

## Repository HEAD (validation run)

Recorded at US-008 validation time (local clones):

| Repository | Commit (full) | Branch |
| ---------- | --------------- | ------ |
| `SecPal/.github` | Tip of [`feat/us-001-reconfirm-drift`](https://github.com/SecPal/.github/pull/412) (see PR head at merge time) | `feat/us-001-reconfirm-drift` |
| `SecPal/api` | `37d8cb93b4abe94e59ca4f065f27f39f3ff37236` | `main` (ahead of `origin/main`) |
| `SecPal/contracts` | `c8116ffb2d589a0b61034bb65fd92e11bf98e5b0` | `main` (ahead of `origin/main`) |
| `SecPal/frontend` | `beee49b1eb34b6203ece2d32524074d392877341` | `main` (tracking `origin/main`) |

Re-run `git rev-parse HEAD` before copying SHAs into a PR description if validation is repeated later.

## Validation evidence

### SecPal/contracts

```bash
cd SecPal/contracts
npm run validate
```

**Result:** Exit code 0 — Redocly lint OK, verified-endpoint presence guard OK (16 operations), Prettier check OK.

### SecPal/api

```bash
cd SecPal/api
php artisan test \
  tests/Feature/AuthTest.php \
  tests/Feature/Controllers/EmployeeDocumentControllerTest.php \
  tests/Feature/Controllers/EmployeeQualificationControllerTest.php \
  tests/Feature/Controllers/QualificationControllerTest.php
```

**Result:** Exit code 0 — 151 tests passed (781 assertions).

### SecPal/frontend

```bash
cd SecPal/frontend
npm run lint
npm run typecheck
npx vitest run src/services/authApi.test.ts src/pages/Employees/EmployeeDetail.test.tsx
```

**Result:** Exit code 0 — ESLint clean, `tsc --noEmit` clean, 79 tests passed across the two files.

**Note:** There are no standalone `employeeDocumentApi` / `qualificationApi` unit files; `EmployeeDetail.test.tsx` mocks those modules and covers list/attach flows at the page level.

### SecPal/.github

```bash
cd SecPal/.github
npm run test:openapi-verified-presence
```

**Result:** Exit code 0 — fixture-based presence guard OK (16 operations).

## E2E and live verification

### Playwright E2E

**Coverage gap (explicit):** There is no dedicated Playwright spec that drives **email verification resend**, **employee document upload/download**, or **employee qualification attach/edit** against a live or staging stack. Existing E2E touches unrelated “verification” wording (e.g. WebAuthn user verification). **Mitigation:** API feature tests and frontend unit tests above exercise the same contracts and UI seams; closing the E2E gap is follow-up work if product requires browser-level regression for these flows.

### Live VPS (`api.secpal.dev`)

Unauthenticated smoke checks (TLS + routing + Laravel JSON envelope) were executed from the validation environment:

| Request | HTTP | Notes |
| ------- | ---- | ----- |
| `GET /v1/qualifications` | 401 | Body `{"message":"Unauthenticated."}` — matches message-only unauthenticated JSON. |
| `GET /v1/employees/{uuid}/documents` | 401 | Same envelope (route reached). |
| `POST /v1/auth/email/verification-notification` | 401 | Same envelope. |

**Blockers for full flow verification:** End-to-end verification of resend throttle (429), multipart upload, and qualification CRUD requires authenticated tenant context (tokens, CSRF/session as applicable), test users, and organization scope — not available in this agent environment. The checks above confirm the deployed API serves the documented routes and auth gate.

## Draft PRs

Open **draft** PRs to `main` for each repository that has unpublished drift-cleanup commits. Suggested titles and bodies:

### `SecPal/contracts`

- **Title:** `feat: OpenAPI contract drift cleanup (US-002–US-007)`
- **Body:** Link this file; summarize commits (presence guard + documented routes); paste contracts validation output; note frontend field-name drift remains for separate SPA work.

### `SecPal/api`

- **Title:** `feat: Contract-aligned tests and RBAC docs (US-003, US-005, US-007)`
- **Body:** Link this file; paste targeted PHPUnit summary; note live VPS 401 smoke only.

### `SecPal/.github`

- **Title:** `feat: Contract drift evidence and OpenAPI guard fixtures (US-001, US-002, US-008)`
- **Body:** Link `US-001-evidence-matrix.md`, `openapi.md`, and this file; paste `npm run test:openapi-verified-presence` result.

### `SecPal/frontend`

No local commits on `main` relative to `origin` in the validated clone — **no draft PR required** for this track unless SPA alignment stories are opened separately.

## Created draft PRs (US-008)

| Repository | Draft PR |
| ---------- | -------- |
| `SecPal/api` | https://github.com/SecPal/api/pull/1005 |
| `SecPal/contracts` | https://github.com/SecPal/contracts/pull/232 |
| `SecPal/.github` | https://github.com/SecPal/.github/pull/412 |

---

Related narrative issues (if tracked): contract drift epic / US-001 analysis; no GitHub issue numbers were validated in this run.
