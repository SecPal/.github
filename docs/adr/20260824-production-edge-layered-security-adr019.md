<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-019: Production Edge and Layered Security

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal architecture rebaseline (August 2026)

## Context

Public ingress needs a single trusted identity and layered enforcement boundary.

## Binding decision

Host-native HAProxy is the sole public edge, with fixed loopback application backends and no container-IP discovery/runtime socket. HAProxy terminates TLS. External Certbot owns ACME: HTTP-01 handling is exact; all other HTTP redirects to HTTPS; publication is atomic, validated with `haproxy -c`, gracefully reloaded, and retains last-known-good material.

Canonical client identity is TCP source. Public clients cannot inject trusted `Forwarded`, XFF, or X-Real-IP semantics. HA may accept PROXY v2 only on a dedicated private listener from allowlisted L4 peers.

Security layers are SELinux/seccomp/capabilities/rootless confinement, nftables, CrowdSec host decisioning, HAProxy CrowdSec SPOA, CrowdSec AppSec/Coraza with pinned OWASP CRS, then application MFA/RBAC/rate limiting. CrowdSec/AppSec/runtime-detector outage is Security **DEGRADED**, not authentication or readiness failure. Runtime process/syscall detection remains technology-neutral pending qualification.

## Relationships and non-goals

This does not choose Falco or Tetragon. See [#695](https://github.com/SecPal/.github/issues/695), ADR-018 and ADR-022.
