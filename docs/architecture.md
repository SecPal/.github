<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# SecPal architecture navigation

Start with the [ADR index](adr/README.md) and the individual decisions'
refinement or supersession notices. For the SecPal product family and current
direction, see [product positioning](product-positioning.md).

## Find the architecture authority

The [ADR index](adr/README.md#index) lists the complete corpus and current status.

| Responsibility                                    | Decisions to read                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Domain and employment                             | [ADR-025](adr/20261002-employment-time-absence-compensation-adr025.md) owns employment, working time, absence, and compensation boundaries. [ADR-014](adr/20260720-tenant-identity-access-model-adr014.md) owns identity, tenant integrity, access, security, and membership lifecycle.                                                                                                                  |
| Identity keys, client trust, and offline recovery | [ADR-015](adr/20260720-global-identity-key-security-adr015.md) covers global identity key security. [ADR-026](adr/20261002-client-trust-offline-recovery-adr026.md) owns USER/WORK client families, endpoint trust, offline authorization, personal-device approval, and recovery. [ADR-012](adr/20260406-single-app-android-distribution-and-private-provisioning-adr012.md) owns Android distribution. |
| Production database and runtime                   | [ADR-017](adr/20260824-postgresql-18-canonical-baseline-adr017.md) and [ADR-018](adr/20260824-production-host-container-runtime-adr018.md).                                                                                                                                                                                                                                                              |
| Edge, high availability, and continuity           | [ADR-019](adr/20260824-production-edge-layered-security-adr019.md) and [ADR-022](adr/20260824-deployment-topology-high-availability-adr022.md).                                                                                                                                                                                                                                                          |
| State, backup, and recovery authorities           | [ADR-020](adr/20260824-production-state-recovery-authority-separation-adr020.md).                                                                                                                                                                                                                                                                                                                        |
| Supply chain and vulnerability evidence           | [ADR-021](adr/20260824-oci-supply-chain-vulnerability-evidence-adr021.md).                                                                                                                                                                                                                                                                                                                               |
| Public/private ownership and managed operations   | [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md) and [ADR-024](adr/20260906-managed-operations-control-plane-authority-adr024.md).                                                                                                                                                                                                                                       |
| Engineering governance                            | [Native GitHub planning and delivery](work-graph-contract.md); ADR-016 owns issue-first planning and native governance.                                                                                                                                                                                                                                                                                  |
| Evidence pipelines and external-system validation | [Evidence and external-system architecture contract](evidence-architecture-contract.md).                                                                                                                                                                                                                                                                                                                 |

## Find implementation and contract owners

| Responsibility                                    | Maintained owner                                                                                                                                                                                                                       |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Integration, portable self-hosting and deployment | [SecPal/deployment](https://github.com/SecPal/deployment#readme) and its [architecture scope](https://github.com/SecPal/deployment/blob/main/docs/architecture/scope.md)                                                               |
| Public HTTP API                                   | [SecPal/contracts](https://github.com/SecPal/contracts#readme)                                                                                                                                                                         |
| API implementation and runtime inputs             | [SecPal/api](https://github.com/SecPal/api#readme) and its [production boundary](https://github.com/SecPal/api/blob/main/docs/deployment.md)                                                                                           |
| Browser application and Android integration       | [SecPal/frontend](https://github.com/SecPal/frontend#readme) and [SecPal/android](https://github.com/SecPal/android#readme)                                                                                                            |
| Managed hosting orchestration and policy          | Private SecPal/operations consumes public deployment contracts under [ADR-023](adr/20260824-public-self-hosting-private-managed-operations-adr023.md) and [ADR-024](adr/20260906-managed-operations-control-plane-authority-adr024.md) |

## Read status and evidence separately

Use the [public status and truth contract](public-status-semantics.md) to
distinguish accepted architecture, delivered source, deployed environments and
operational qualification. For delivery, follow the current issues and evidence
in the owning repository.
