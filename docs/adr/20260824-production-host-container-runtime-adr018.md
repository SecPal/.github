<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-018: Production Host and Container Runtime

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

The production runtime requires one auditable host and containment baseline.

## Binding decision

The reference host is Rocky Linux 10.2+; x86 hosts require x86-64-v3 and arm64 is separately qualified. SELinux enforcing with `container-selinux` is mandatory. Product runtime uses rootless Podman with systemd/Quadlet. Production has no Docker Engine/Compose path, rootful fallback, runtime socket/API dependency, host networking, or mutable/tag-based OCI consumption. Product containers expose only explicitly bounded interfaces and consume immutable digest-only artifacts.

Host OS and OCI userspace/base image are separate decisions: Rocky does not require Rocky/UBI application images.

## Consequences and non-goals

After successor evidence, obsolete Debian/AppArmor/Docker/Compose paths are removed rather than compatibility obligations. This ADR does not select application base images or a builder.

## Relationships

See [#695](https://github.com/SecPal/.github/issues/695), [#698](https://github.com/SecPal/.github/issues/698), ADR-019 and ADR-021.
