<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-011: Simplify Management Level from Model to Integer Field

**Status:** Employee master-data decision remains accepted. Authorization is
governed by [ADR-014](20260720-tenant-identity-access-model-adr014.md).

**Date:** 2025-12-27

**Deciders:** @kevalyq

## Decision

Use a simple `management_level` integer on the Employee record. The range is
`0`–`255`, with `0` for employees without a management level and `1` as the
highest descriptive management level. Keep this as employee master data. A
separate `LeadershipLevel` model, table, and administration API are unnecessary.

[ADR-014](20260720-tenant-identity-access-model-adr014.md) governs access through
an active tenant membership and explicit permission, scope and validity.
A management level grants no functional rights.
