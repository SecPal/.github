<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# ADR-012: Android Distribution

**Status:** Accepted for distribution. [ADR-026](20261002-client-trust-offline-recovery-adr026.md)
owns client, signing, and endpoint identity.

**Date:** 2026-04-06

**Decision authority:** @aroviqen

## Decision

- Support Play Store, GitHub Releases, Obtainium, and direct APK distribution.
- Play Store installations use Play-native updates.
- Use `apk.secpal.app` as the canonical host for APKs, checksums, Stable/Beta
  metadata and other machine-readable release metadata. GitHub Releases,
  Obtainium, and direct APK installations use that host and its metadata.
- Support Stable and Beta as release tracks and public metadata paths.
- Use `secpal.app/android` as the human-facing Android landing surface.
- Keep long-lived secrets out of public distribution artifacts.

Release implementations select channels per application identity under ADR-026.
The distribution routes do not require publication of every identity through
every channel or a shared version line.
