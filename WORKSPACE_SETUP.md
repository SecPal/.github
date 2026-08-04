<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Workspace

This is the multi-repository workspace for the SecPal project.

## Repository Structure

```
SecPal/
├── .github/       # Organization-wide settings and documentation
│   └── setup-hooks.sh  # Master script to setup hooks in all repos
├── api/           # Laravel backend API
├── android/       # React/TypeScript Android app via Capacitor
├── contracts/     # OpenAPI 3.1 API specifications
├── frontend/      # React/TypeScript frontend application
└── secpal.app/    # Astro public website
```

## Quick Setup

After cloning all repositories, run the master setup script from the `.github` repository:

```bash
cd .github
./setup-hooks.sh
```

This will:

- Install pre-commit (if not already installed)
- Set up pre-commit hooks in all active repos (formatting, linting, REUSE compliance)
- Set up commit-message hygiene hooks in all active repos
- Retire legacy SecPal-managed full-preflight `pre-push` symlinks while
  preserving custom hooks

## Individual Repository Setup

If you need to set up hooks for a specific repository:

```bash
cd <repository>

# Install pre-commit (if not already installed)
pip install --user pre-commit

# Install pre-commit hooks
./scripts/setup-pre-commit.sh

```

## Android Toolchain

For the `android/` repository, hooks alone are not enough. Local and
Polyscope-driven Gradle runs also need a discoverable Android toolchain:

- Java 21
- `adb`
- `sdkmanager`
- an Android SDK under `$HOME/Android/Sdk`, or explicit `ANDROID_SDK_ROOT` /
  `ANDROID_HOME`

If you are provisioning or restoring a workspace machine, verify that baseline
from `.github` with:

```bash
./scripts/check-system-requirements.sh --repo=android
```

Polyscope rollout now writes `android/local.properties` automatically for
Android workspaces, using `POLYSCOPE_ANDROID_SDK_ROOT`, `ANDROID_SDK_ROOT`,
`ANDROID_HOME`, or the default `$HOME/Android/Sdk` path in that order. That
keeps direct `./gradlew ...` runs from failing when the shell environment was
not preloaded explicitly.

## Hook Architecture

SecPal uses fast commit-time hooks. Full validation remains an explicit action
instead of blocking every push.

### Pre-commit Hooks

- Managed by the [Python pre-commit framework](https://pre-commit.com/)
- Runs on every `git commit`
- Checks: Prettier, markdownlint, yamllint, actionlint, ShellCheck, REUSE compliance
- Configuration: `.pre-commit-config.yaml` in each repo

### Full Validation

- Run the smallest relevant checks while iterating.
- Use Polyscope's single `All Checks` action or `./scripts/preflight.sh` for an
  intentional complete local pass before handoff when warranted.
- Push does not repeat the full suite. Repository-specific custom `pre-push`
  hooks remain supported and are not removed by SecPal automation.

Workflow linting via `actionlint` is enforced through pre-commit hooks and CI. If you need to run it manually, prefer `pre-commit run actionlint --all-files`, or wrap any direct `actionlint` invocation in a short timeout (e.g. `timeout 30 actionlint`) to avoid environment-specific hangs.

If `./scripts/preflight.sh` reports that `actionlint` is not installed, that only affects direct manual `actionlint` runs. After `./setup-hooks.sh`, the supported local path remains `pre-commit run actionlint --all-files`. Install the standalone binary only if you also want direct CLI usage, for example via `go install github.com/rhysd/actionlint/cmd/actionlint@latest`.

Do not bypass the remaining hooks. Fix a failing commit-time check instead.

## Documentation

- [Git Hook Setup & Troubleshooting](docs/HOOK_SETUP_TROUBLESHOOTING.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Development Workflow](README.md)

## License

This project is licensed under AGPL-3.0-or-later. See individual repositories for detailed license information.
