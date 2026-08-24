<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0 -->

# ADR-019: Production Edge and Layered Security

**Status:** Accepted
**Date:** 2026-08-24
**Decision authority:** SecPal maintainers

**Decision provenance:** This ADR records architecture decisions deliberately
adopted during the August 2026 rebaseline. 2026-08-24 is the durable ADR record
date, not an assertion that this PR first made those decisions.

## Context

Public ingress needs a single trusted identity and layered enforcement boundary.

## Binding decision

Host-native HAProxy is the sole public edge, with fixed loopback application backends and no container-IP discovery/runtime socket. HAProxy terminates TLS. External Certbot owns ACME: HTTP-01 handling is exact; all other HTTP redirects to HTTPS; publication is atomic, validated with `haproxy -c`, gracefully reloaded, and retains last-known-good material.

Canonical client identity is TCP source. Public clients cannot inject trusted `Forwarded`, XFF, or X-Real-IP semantics. Permanent HA may expose a dedicated private HAProxy listener accepting PROXY v2 only from allowlisted L4 load-balancer peers; public/direct bypass is not trusted. TLS 1.2 and TLS 1.3, HTTP/2, and HTTP/1.1 are the reference protocols; this ADR makes no HTTP/3 commitment.

Security layers are SELinux/seccomp/capabilities/rootless confinement, nftables, CrowdSec host decisioning, HAProxy CrowdSec SPOA, CrowdSec AppSec/Coraza with pinned OWASP CRS, then application MFA/RBAC/rate limiting. CrowdSec/AppSec/runtime-detector outage is Security **DEGRADED**, not authentication or readiness failure. Runtime process/syscall detection remains technology-neutral pending qualification. The self-hosted reference uses a local CrowdSec Security Engine/LAPI without mandatory Central, Console, community, or premium threat-intelligence data; managed external-data use is a separate licensing/rights decision.

## Consequences

Only HAProxy is public and trusted client identity has one canonical source.
Security-signal outages remain visible and operationally actionable without
silently changing application authentication or readiness semantics.

## Relationships and non-goals

This does not choose Falco or Tetragon. See [#695](https://github.com/SecPal/.github/issues/695), ADR-018 and ADR-022.
