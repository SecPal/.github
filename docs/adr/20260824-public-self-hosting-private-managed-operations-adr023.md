<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-023: Public Self-Hosting vs Private Managed Operations Boundary

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

Public self-hosting must remain secure and recoverable without depending on managed-provider knowledge.

## Binding decision

Public `SecPal/deployment` and other public product repositories own everything required to build, understand, self-host, secure, update, recover, and verify SecPal correctly. Private `SecPal/operations` owns managed-provider-specific topology, provisioning/fleet automation, tuning, managed monitoring/detection/remediation, capacity/cost, customer lifecycle, and managed operating procedures.

Neither public nor private Git may hold secrets, credentials, private keys, customer data, backup-decryption authorities, or mutable live infrastructure state that itself acts as secret/control-plane authority. Private Git is not a secret store.

## Consequences and boundaries

Managed operations may add provider-specific capability without becoming a hidden dependency for public deployment. This ADR does not publish managed-provider details or relax any authority boundary.

## Relationships

Codifies [#695](https://github.com/SecPal/.github/issues/695); see ADR-020 and ADR-022.
