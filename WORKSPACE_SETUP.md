<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal workspace setup

Product work runs in Codex CLI on `secpal.dev` inside Herdr. Use the assigned
repository tabs and preserve work already in progress. Start a new private
full-stack workspace from the requesting Herdr session when one is needed:

```bash
secpal-order new NAME --profile secpal
```

The full-stack profile provisions isolated checkouts, a database, API and
frontend behind `https://NAME.preview.secpal.dev`. Website work on secpal.app
uses `--profile website`.

- `secpal-order resume NAME` returns to the assigned workspace.
- `secpal-order stop NAME` frees runtime capacity and preserves work.
- `secpal-order start NAME` republishes a stopped workspace.
- `secpal-order finish NAME` releases a completed assignment after protected
  GitHub delivery. Preserve dirty files, unpublished commits and open PR work.

Use local Codex on `840G11` for separately authorized infrastructure administration.

## Repository checks

Read the target checkout's `AGENTS.md`. For local checkouts, install the
repository's hooks with `./scripts/setup-pre-commit.sh` where available.
Run the smallest relevant checks while iterating and use the repository's
preflight for complete local validation when applicable. GitHub reviews,
required checks and protected merges govern delivery.

Android Gradle work needs Java 21 and a discoverable Android SDK with
`adb` and `sdkmanager`. Set `ANDROID_SDK_ROOT` or `ANDROID_HOME` if the SDK is
outside `~/Android/Sdk`. Verify the toolchain with
`./scripts/check-system-requirements.sh --repo=android` from this repository.
