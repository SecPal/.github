<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-018: Production Host and Container Runtime

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

The 2026-11-19 Managed refinement under
[#1347](https://github.com/SecPal/.github/issues/1347) replaces the Rocky
reference with Fedora CoreOS and admits qualified container infrastructure.
Earlier Rocky deliveries remain evidence for their original scope.

## Context

The production runtime requires one auditable host and containment baseline.

## Binding decision

The primary Managed reference host is Fedora CoreOS Stable, with independently
qualified x86_64 and aarch64 artifacts. The x86 reference retains the
x86-64-v3 admission requirement. SELinux Enforcing, effective container process
and persistent-storage labels, cgroup v2 and qualified subordinate IDs and
rootless networking remain mandatory. Product runtime uses rootless Podman with
systemd/Quadlet. Administrator-owned definitions remain outside runtime-account
write authority.

Application and infrastructure services use Podman/Quadlet wherever technically
appropriate. PostgreSQL 18, HAProxy and CrowdSec are infrastructure components,
not application-container authority. Rootless is the default. An infrastructure
component requiring host integration must separately prove its minimum host
privileges, identities, interfaces, storage labels and failure behavior. A
rootful exception requires explicit component-specific qualification; it grants
no rootful fallback to product workloads and no general privileged container.
Host firewall and recovery authority remain independently available.

Product containers have no Docker Engine/Compose path, runtime socket/API
dependency, host networking or mutable/tag-based OCI consumption. Infrastructure
containerization does not relax these boundaries by implication. Every selected
OCI index/platform artifact is digest-pinned and qualified under ADR-021.
Host OS and OCI userspace/base image remain separate decisions; Fedora CoreOS
does not require Fedora application images.

### Provisioning and updates

Provisioning uses version-pinned, publisher-verified architecture-specific OS
artifacts and validated Butane/Ignition inputs. Reinstallation generates fresh
host, SSH and management-peer identities; an ordinary reboot preserves them.
Provider resource identity and host installation identity are separate facts.
Reusable bootstrap secrets do not belong in Ignition, images, repositories or
logs. Authenticated bootstrap and independent provider Rescue/Console recovery
remain available without a working private management tunnel. Private network
connectivity is not Host Identity or Workload Authorization.

rpm-ostree/Zincati update and reboot policy is explicit and versioned. Disruptive
automatic updates remain disabled during qualification. Production rolling
updates require independently qualified availability, fencing, reboot,
reconnection and rollback behavior. An OS rollback does not roll back persistent
database state or authorize a database/schema downgrade.

Host provisioning and Host Conformance precede Host Enrollment and subsequent
workload-scoped Workload Activation. Provisioning a host does not grant it
deployment, secret, database, backup or recovery authority.

### Qualification and portability

Existing bounded test evidence covers signed FCOS installation, fresh
installation identities, authenticated SSH, direct WireGuard management,
rootless Podman/Quadlet, SELinux Enforcing and reboot persistence on x86_64 and
aarch64. The x86_64 rebuild qualification also covers repeated complete guest
replacement and generation-aware peer replacement. Live inventory and raw
operational evidence remain private; they are not public architecture inputs.

Host qualification is not Managed Production Acceptance. It does not qualify
production application confinement, PostgreSQL durability or TLS, backup,
RecoverySets, HA/fencing, infrastructure privileges, rolling updates or
independent-provider continuity. Those contracts need their own real-system
evidence, including effective SELinux isolation and negative access tests.

Self-hosting does not require Fedora CoreOS. Portable runtime, storage, security,
enrollment and recovery capabilities remain public; live Managed fleet
composition remains private under ADR-023/024. This decision creates no promise
of an unqualified alternate OS matrix and no second orchestration, VPN or
identity platform.

## Consequences and non-goals

After successor evidence, superseded executable platform paths are retired
rather than maintained as automatic compatibility obligations. Historical Rocky
qualification must not be relabeled as FCOS or container-infrastructure proof.
This ADR does not select application base images or a builder, migrate the
development host, or authorize customer-production rollout.

## Relationships

See [#695](https://github.com/SecPal/.github/issues/695),
[#1347](https://github.com/SecPal/.github/issues/1347), ADR-017, ADR-019,
ADR-020, ADR-021, ADR-022, ADR-023 and ADR-024.
