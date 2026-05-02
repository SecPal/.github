<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-012: Single-App Android Distribution and Private Provisioning QR Architecture

## Status

**Accepted** (Epic #327, PR-0 / Issue #328)

## Date

2026-04-06

## Deciders

@aroviqen

## Context

SecPal needs one Android distribution model that works for normal installs and managed Device Owner provisioning without splitting the product into multiple Android packages.

The delivery model must support:

- Play Store distribution
- GitHub Releases and Obtainium distribution
- direct APK downloads
- Device Owner provisioning during Android setup

At the same time, SecPal must avoid publishing reusable provisioning QR codes or embedding long-lived secrets in public Android distribution artifacts.

## Decision

SecPal standardizes on one Android application package, `app.secpal`, with one signing identity and one version line across all Android distribution channels.

The channel split is:

- `apk.secpal.app` is the canonical technical host for APKs, checksums, and release metadata.
- `secpal.app/android` is the human-facing Android landing surface.
- Play Store installs continue to use Play-native update flows.
- GitHub Releases, Obtainium, and direct APK installs use the canonical artifact host and release metadata.
- Device Owner provisioning uses the same app package and exchanges a short-lived bootstrap token for tenant-specific configuration after enrollment starts.

Provisioning QR rules are:

- provisioning QR codes are generated only inside SecPal for authorized users
- QR payloads stay minimal and contain bootstrap metadata plus a short-lived bootstrap token
- public generic provisioning QR codes are not allowed
- long-lived provisioning secrets or tenant policy blobs must not be embedded in QR payloads

## Consequences

### Positive

- Android distribution stays consistent across public and managed rollout channels.
- Users and administrators see one package name and one version line instead of channel-specific app variants.
- The artifact host and the human-facing landing flow are clearly separated.
- Provisioning becomes auditable and permission-gated instead of relying on public static QR payloads.

### Negative

- Bootstrap token exchange now becomes a required backend and contract capability before managed provisioning is complete.
- Multiple repositories must align on the same artifact-host and provisioning model.
- The public website and Android client must remain explicit about channel-specific update behavior.

## Repo-Local Follow-Up Impact

- `.github` updates the organization-wide domain policy, governance text, and validation baseline in [Issue #328](https://github.com/SecPal/.github/issues/328).
- `api` implements enrollment sessions, bootstrap tokens, and audited provisioning APIs in [Issue #800](https://github.com/SecPal/api/issues/800).
- `contracts` specifies enrollment, bootstrap, and release metadata contracts in [Issue #183](https://github.com/SecPal/contracts/issues/183).
- `frontend` adds permission-gated provisioning QR generation and enrollment management UI in [Issue #751](https://github.com/SecPal/frontend/issues/751).
- `android` implements enrollment-token bootstrap and channel-aware provisioning/update handling in [Issue #102](https://github.com/SecPal/android/issues/102).
- `secpal.app` publishes stable Android download endpoints and the human-facing Android landing flow in [Issue #46](https://github.com/SecPal/secpal.app/issues/46).

## Alternatives Considered

1. **Split Android distribution into multiple packages**

   - Pro: clearer separation between managed and unmanaged installs
   - Contra: breaks the single-product experience and complicates signing, updates, and support

2. **Publish a public static provisioning QR code**

   - Pro: simpler first rollout
   - Contra: exposes provisioning data publicly and does not support audited, permission-gated enrollment

3. **Use `secpal.app/android` as both landing page and artifact host**
   - Pro: fewer hostnames to explain
   - Contra: mixes human-facing navigation with stable machine-facing artifact and metadata delivery

## Related

- [Epic #327](https://github.com/SecPal/.github/issues/327)
- [Issue #328](https://github.com/SecPal/.github/issues/328)
