<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal architecture navigation

Start with the [ADR index](adr/README.md) for current architecture status, then
read the individual decisions and their refinement or supersession notices.
The index and individual ADRs own architecture status and content. This page
only routes readers to those authorities and repository-owned contracts.

For product direction, use [product positioning](product-positioning.md); for
current product-family identity, use
[BRAND-0007](adr/BRAND-0007-secpal-product-family-architecture.md).

## Find the architecture authority

The routes below group responsibilities rather than delivery order. Consult the
[canonical index](adr/README.md#index) for the complete corpus and current status;
these routes do not maintain a second status catalog.

| Responsibility                                    | Decisions to read                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Domain and employment                             | [ADR-025](adr/20261002-employment-time-absence-compensation-adr025.md) owns employment, working time, absence, and compensation boundaries. [ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) retains identity, tenant integrity, access, security, and remaining membership decisions. Its Employee contract projection, projection-derived membership employment bases and lifecycle inputs, and unresolved rehire boundary are Partially Superseded by ADR-025. |
| Identity keys, client trust, and offline recovery | [ADR-015](adr/20260720-global-identity-key-security-adr015.md) covers global identity key security. [ADR-026](adr/20261002-client-trust-offline-recovery-adr026.md) owns USER/WORK client families, endpoint trust, offline authorization, personal-device approval, and recovery. [ADR-012](adr/20260406-single-app-android-distribution-and-private-provisioning-adr012.md) is Partially Superseded; read its retained distribution scope alongside ADR-026.                  |
| Production database and runtime                   | [ADR-017](adr/20260824-postgresql-18-canonical-baseline-adr017.md) and [ADR-018](adr/20260824-production-host-container-runtime-adr018.md).                                                                                                                                                                                                                                                                                                                                     |
| Edge, high availability, and continuity           | [ADR-019](adr/20260824-production-edge-layered-security-adr019.md) and [ADR-022](adr/20260824-deployment-topology-high-availability-adr022.md).                                                                                                                                                                                                                                                                                                                                 |
| State, backup, and recovery authorities           | [ADR-020](adr/20260824-production-state-recovery-authority-separation-adr020.md).                                                                                                                                                                                                                                                                                                                                                                                               |
| Supply chain and vulnerability evidence           | [ADR-021](adr/20260824-oci-supply-chain-vulnerability-evidence-adr021.md).                                                                                                                                                                                                                                                                                                                                                                                                      |
| Public/private ownership and managed operations   | [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md) and [ADR-024](adr/20260906-managed-operations-control-plane-authority-adr024.md).                                                                                                                                                                                                                                                                                                              |
| Engineering governance                            | [ADR-016](adr/20260824-native-work-graph-engineering-governance-adr016.md) and its [work-graph contract](work-graph-contract.md).                                                                                                                                                                                                                                                                                                                                               |
| Evidence pipelines and external-system validation | [Evidence and external-system architecture contract](evidence-architecture-contract.md).                                                                                                                                                                                                                                                                                                                                                                                        |

ADR-015 through ADR-026 are Accepted. Acceptance defines binding architecture;
it does not establish implementation, platform qualification, or production
operation, including for ADR-024's Managed Operations Control Plane.

## Find implementation and contract owners

Repository-owned contracts describe supported implementation and procedures
within the accepted architecture. Follow their current evidence and owning work
before making implementation or operational claims.

| Responsibility                                                                                                       | Maintained owner and entry point                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration, self-hosting, production deployment, security integration, backup, recovery, updates, and qualification | [SecPal/deployment](https://github.com/SecPal/deployment#readme), its [architecture scope](https://github.com/SecPal/deployment/blob/main/docs/architecture/scope.md), and [integration contract](https://github.com/SecPal/deployment/blob/main/docs/quadlet-integration.md). The documentation rebaseline [#127](https://github.com/SecPal/deployment/issues/127) is completed; maintained docs distinguish delivered integration from accepted production architecture and remaining work. |
| Public HTTP API                                                                                                      | [SecPal/contracts](https://github.com/SecPal/contracts#readme) owns the exact public API contract where applicable.                                                                                                                                                                                                                                                                                                                                                                           |
| API application and image/container requirements                                                                     | [SecPal/api](https://github.com/SecPal/api#readme) owns implementation and repository-local documentation. Its deployment/container documentation rebaseline [#1453](https://github.com/SecPal/api/issues/1453) remains open; older guidance must be read against current ADRs and deployment contracts.                                                                                                                                                                                      |
| Application UI and Android/native behavior                                                                           | [SecPal/frontend](https://github.com/SecPal/frontend#readme) and [SecPal/android](https://github.com/SecPal/android#readme) own their implementations and local contracts; ADR-026 acceptance does not prove client behavior delivered.                                                                                                                                                                                                                                                       |
| SecPal Managed orchestration and policy                                                                              | Private SecPal/operations owns the managed delta under public [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md) and [ADR-024](adr/20260906-managed-operations-control-plane-authority-adr024.md).                                                                                                                                                                                                                                                              |

Under ADR-023, public repositories own the portable technical capabilities and
contracts required for independent operation and self-hosting. SecPal Managed
adds private customer/fleet/commercial policy and orchestration, consuming those
public contracts. Private Managed artifacts must not become a hidden technical
dependency for independent operation. This ownership decision does not claim
that every public capability or private managed system is already implemented.

## Read status and evidence separately

The [public status and truth contract](public-status-semantics.md) owns claim
classification and evidence requirements. Its classes are independent dimensions:
Accepted Architecture does not establish Implemented in Source; source
implementation does not establish Operationally / Externally Verified; verification
does not establish deployment; Deployed to Development / Test does not establish
Production Deployment or Production Operation. Even Production Deployment alone
does not establish Production Operation.

Architecture recorded through [#695](https://github.com/SecPal/.github/issues/695)
and [#717](https://github.com/SecPal/.github/issues/717), including the ownership
refinement [#748](https://github.com/SecPal/.github/issues/748), is distinct from
implementation and qualification tracked beneath the current native work graph,
including [#747](https://github.com/SecPal/.github/issues/747). Follow owning
issues and current repository evidence for that state. An open issue or Planned /
Tracked Work does not establish Active Implementation or a delivery promise.
Missing or stale evidence requires a narrower truthful claim, as the status
contract specifies.

## Read proposed and historical material

The ADR index retains [Proposed](adr/README.md#proposed),
[Partially Superseded](adr/README.md#partially-superseded), and
[Superseded](adr/README.md#superseded) decisions. Proposed Guard Book
[ADR-001](adr/20251027-event-sourcing-for-guard-book.md) and OpenTimestamp
[ADR-002](adr/20251027-opentimestamp-for-audit-trail.md) are non-binding until
Accepted. Offline-first [ADR-003](adr/20251027-offline-first-architecture.md) is
Superseded by ADR-026; its original Proposed body is historical, never-Accepted
evidence, not current offline architecture.

Historical ADR bodies record decisions and proposals at their time. Current
status, refinement, and supersession metadata determine binding scope: Partially
Superseded decisions bind only in their retained scope; Superseded material is
not current execution guidance. Git history, issues, PRs, and
[deployment's historical records](https://github.com/SecPal/deployment#historical-evidence)
remain discoverable evidence; they do not independently establish current
authority or a current supported path.
