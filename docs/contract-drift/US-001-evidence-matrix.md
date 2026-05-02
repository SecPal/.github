<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# US-001: Contract drift evidence (reconfirmed against `main`)

This matrix was produced by pulling latest `main` in `SecPal/api`, `SecPal/frontend`, `SecPal/contracts`, and `SecPal/.github`, then comparing backend routes, the frontend HTTP client, and `SecPal/contracts` `docs/openapi.yaml`. No product code was changed for this story.

**Note (US-007):** Later contract work added qualification catalog and employee-qualification assignment paths to `SecPal/contracts` `docs/openapi.yaml`. The tables below remain a **frozen US-001 snapshot** for reproducibility; OpenAPI coverage cells are superseded for those routes — use the current spec and backend for authoritative behavior.

## Snapshot (reproducibility)

| Repository  | `main` at time of check (short SHA) |
| ----------- | ----------------------------------- |
| `api`       | `8da999a`                           |
| `frontend`  | `beee49b`                           |
| `contracts` | `f4b4491`                           |
| `.github`   | `3b49e7e`                           |

## Route and client surface (base path `/v1`, plus global API prefix as deployed)

### Qualification catalog (`QualificationController`)

| Method   | Path                              | Backend (Laravel)                                                                                                            | Frontend (`src/services/qualificationApi.ts`)                                                                           | OpenAPI `docs/openapi.yaml` |
| -------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| `GET`    | `/qualifications`                 | `QualificationController@index` — query: `is_system_qualification`, `category`, `is_mandatory`                               | `fetchQualifications` — `is_system_qualification`, `category` only (no `is_mandatory`)                                  | **Missing**                 |
| `POST`   | `/qualifications`                 | `store` — body: `name`, `description`, `category`, `requires_renewal`, `renewal_period_months`, `is_mandatory`, `sort_order` | `createQualification` — `QualificationFormData` uses `requires_certificate`, `has_expiry_date` (not server field names) | **Missing**                 |
| `GET`    | `/qualifications/{qualification}` | `show`                                                                                                                       | `fetchQualification`                                                                                                    | **Missing**                 |
| `PATCH`  | `/qualifications/{qualification}` | `update`                                                                                                                     | `updateQualification` (same form shape as create)                                                                       | **Missing**                 |
| `DELETE` | `/qualifications/{qualification}` | `destroy`                                                                                                                    | `deleteQualification`                                                                                                   | **Missing**                 |

**OpenAPI:** `rg` over `docs/openapi.yaml` finds no `qualification` string; the contract file does not document this catalog or any of the paths above.

**Related drift (qualification resource shape):** `QualificationResource` exposes `requires_renewal`, `renewal_period_months`, `is_mandatory`, `tenant_id`, `sort_order`, timestamps. The frontend `Qualification` type uses `requires_certificate` and `has_expiry_date` and omits several of those fields — types and wire format do not match the API model.

**Index query drift:** `IndexQualificationRequest` allows `category` value `custom`; the frontend `QualificationCategory` union does not include `custom`.

### Employee–qualification assignments (`EmployeeQualificationController`)

| Method   | Path                                               | Backend                                                                 | Frontend (`qualificationApi.ts`)                                                               | OpenAPI     |
| -------- | -------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ----------- |
| `GET`    | `/employees/{employee}/qualifications`             | `index`                                                                 | `fetchEmployeeQualifications`                                                                  | **Missing** |
| `POST`   | `/employees/{employee}/qualifications`             | `store` — `AttachQualificationRequest`: `obtained_date`, …              | `attachQualification` — `AttachQualificationData` uses **`issued_date`** (not `obtained_date`) | **Missing** |
| `GET`    | `/employee-qualifications/{employeeQualification}` | `show`                                                                  | _No dedicated client function_                                                                 | **Missing** |
| `PATCH`  | `/employee-qualifications/{employeeQualification}` | `update` — `UpdateEmployeeQualificationRequest`: **`obtained_date`**, … | `updateEmployeeQualification` — uses `Partial<AttachQualificationData>` (**`issued_date`**)    | **Missing** |
| `DELETE` | `/employee-qualifications/{employeeQualification}` | `destroy`                                                               | `detachQualification`                                                                          | **Missing** |

**OpenAPI:** No paths under `/qualifications`, `/employees/{employee}/qualifications`, or `/employee-qualifications/{…}` appear in the specification (employee section includes `/employees/{employee}` CRUD and related flows, but not nested qualifications).

**Field-name drift:** Responses use `obtained_date` (`EmployeeQualificationResource`). The frontend `EmployeeQualification` interface documents **`issued_date`** instead of `obtained_date`, and attach/update payloads use **`issued_date`**, which does not match `AttachQualificationRequest` / `UpdateEmployeeQualificationRequest` validation rules.

**Status enum drift:** Backend allows `valid`, `expiring_soon`, `expired` for assignment `status`. Frontend `EmployeeQualification.status` is `"valid" \| "expired" \| "pending"` — `expiring_soon` and `pending` are inconsistent with the API.

**UI usage note:** `EmployeeDetail.tsx` currently imports only `fetchEmployeeQualifications` (read path). Other client helpers exist but are not referenced from that page; any UI that starts calling attach/update will hit the payload naming mismatches above unless corrected.

## File references (evidence)

### Backend (`api`)

- Routes: `routes/api.php` (qualification and employee-qualification groups under `tenant.inject`).
- Controllers: `app/Http/Controllers/Api/V1/QualificationController.php`, `app/Http/Controllers/Api/V1/EmployeeQualificationController.php`.
- Requests: `app/Http/Requests/IndexQualificationRequest.php`, `StoreQualificationRequest.php`, `UpdateQualificationRequest.php`, `AttachQualificationRequest.php`, `UpdateEmployeeQualificationRequest.php`.
- Resources: `app/Http/Resources/QualificationResource.php`, `app/Http/Resources/EmployeeQualificationResource.php`.

### Frontend (`frontend`)

- Client: `src/services/qualificationApi.ts`.
- Current qualifications UI consumer: `src/pages/Employees/EmployeeDetail.tsx` (list fetch only).

### Contract (`contracts`)

- OpenAPI: `docs/openapi.yaml` — **no** qualification or employee-qualification assignment paths documented at the time of this check.

## Summary for contract work

1. **OpenAPI paths (historical vs current):** At the time of US-001, qualification and employee-qualification CRUD were absent from `docs/openapi.yaml`. Those paths are now documented in the contracts repo; use the live spec for coverage.
2. **Additional drift to qualify when documenting or aligning clients:** qualification field names (`requires_renewal` vs `requires_certificate`, etc.), attach/update date field (`obtained_date` vs `issued_date`), optional `is_mandatory` list filter, `custom` category, assignment `status` values, and response shape vs frontend types.
