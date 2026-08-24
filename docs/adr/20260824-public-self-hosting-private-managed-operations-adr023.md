<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-023: Public Self-Hosting vs Private Managed Operations Boundary

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

Public self-hosting must remain secure and recoverable without depending on managed-provider knowledge.

## Binding decision

Public `SecPal/deployment` and other public product repositories own everything required to build, understand, self-host, secure, update, recover, and verify SecPal correctly. Private `SecPal/operations` owns managed-provider-specific topology, provisioning/fleet automation, tuning, managed monitoring/detection/remediation, capacity/cost, customer lifecycle, and managed operating procedures.

Neither public nor private Git may hold secrets, credentials, private keys, customer data, backup-decryption authorities, or mutable live infrastructure state that itself acts as secret/control-plane authority. Private Git is not a secret store.

## Consequences and boundaries

Managed operations may add provider-specific capability without becoming a hidden dependency for public deployment. This ADR defines the architecture ownership boundary; it does not claim that `SecPal/operations` is currently an executable, privileged production operations control plane. Under [#705](https://github.com/SecPal/.github/issues/705), that repository is currently information/architecture collection. Before it gains executable or privileged production automation or live control-plane responsibility, a separate governance/security-hardening contract must be accepted. This ADR does not bypass that requirement.

## Relationships

Codifies [#695](https://github.com/SecPal/.github/issues/695); see [#705](https://github.com/SecPal/.github/issues/705), ADR-020, and ADR-022.
