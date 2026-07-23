<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-012: Single-App Android Distribution and Private Provisioning QR Architecture

## Status

**Partially superseded by [Epic #586](https://github.com/SecPal/.github/issues/586)**
([Issue #587](https://github.com/SecPal/.github/issues/587)); the Android
distribution decisions identified below remain accepted.

## Supersession Notice

Epic #586 supersedes the frontend-issued Android enrollment and provisioning
part of this ADR:

- frontend-generated provisioning QR or URL payloads;
- API enrollment sessions and bootstrap-token exchange;
- contracts for those enrollment and bootstrap surfaces; and
- native enrollment-token coordination that depended on those surfaces.

Those decisions and their repository follow-ups are retired. They are neither
accepted architecture nor planned work.

The following distribution decisions remain accepted:

- one Android application package, `app.secpal`, with one signing identity and
  one version line;
- Play Store, GitHub Releases, Obtainium, and direct APK distribution;
- `apk.secpal.app` as the canonical host for APKs, checksums, Stable/Beta
  metadata, and other machine-readable release metadata;
- Stable and Beta as the supported release tracks and public metadata paths;
- `secpal.app/android` as the human-facing Android landing surface; and
- the same signed application package for normal, Device Owner, and
  profile-owner operation.

Epic #586 does not redefine Android package/signing identity, distribution
routes, release-track metadata, or native Device Owner/profile-owner semantics.

## Date

2026-04-06

## Deciders

@aroviqen

## Context

SecPal needs one Android distribution model that works for normal installs and
managed Android deployments without splitting the product into multiple Android
packages.

The delivery model must support:

- Play Store distribution
- GitHub Releases and Obtainium distribution
- direct APK downloads
- Device Owner and profile-owner operation

## Decision

SecPal standardizes on one Android application package, `app.secpal`, with one
signing identity and one version line across all Android distribution channels.

The channel split is:

- `apk.secpal.app` is the canonical technical host for APKs, checksums,
  Stable/Beta metadata, and other machine-readable release metadata.
- `secpal.app/android` is the human-facing Android landing surface.
- Play Store installs continue to use Play-native update flows.
- GitHub Releases, Obtainium, and direct APK installs use the canonical artifact
  host and release metadata.
- Stable and Beta retain their existing public paths and metadata contracts.
- Normal, Device Owner, and profile-owner operation use the same signed
  application package.

## Consequences

### Positive

- Android distribution stays consistent across public and managed rollout channels.
- Users and administrators see one package name and one version line instead of channel-specific app variants.
- The artifact host and the human-facing landing flow are clearly separated.

### Negative

- Multiple repositories must align on the same artifact-host and release-metadata
  model.
- The public website and Android client must remain explicit about channel-specific update behavior.

## Repo-Local Follow-Up Impact

- `.github` updates the organization-wide domain policy, governance text, and validation baseline in [Issue #328](https://github.com/SecPal/.github/issues/328).
- `android` uses the accepted package/signing identity and Stable/Beta release
  metadata without changing Device Owner or profile-owner semantics.
- `secpal.app` publishes stable Android download endpoints and the human-facing
  Android landing flow in [Issue #46](https://github.com/SecPal/secpal.app/issues/46).

## Alternatives Considered

1. **Split Android distribution into multiple packages**

   - Pro: clearer separation between managed and unmanaged installs
   - Contra: breaks the single-product experience and complicates signing, updates, and support

2. **Use `secpal.app/android` as both landing page and artifact host**

   - Pro: fewer hostnames to explain
   - Contra: mixes human-facing navigation with stable machine-facing artifact and metadata delivery

## Related

- [Epic #327](https://github.com/SecPal/.github/issues/327)
- [Issue #328](https://github.com/SecPal/.github/issues/328)
- [Epic #586](https://github.com/SecPal/.github/issues/586)
- [Issue #587](https://github.com/SecPal/.github/issues/587)
