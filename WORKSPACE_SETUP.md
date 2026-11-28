<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal workspace setup

Product work runs in Codex CLI on `secpal.dev` inside Herdr. Use the assigned
repository tabs and preserve work already in progress. Run new assignments from
the requesting Herdr session.

## Issue-bound repository assignments

Use the repository and issue number of the work selected in GitHub. For example,
start the Contracts delivery for SecPal/contracts#614 with:

```bash
secpal-order new contracts-614 --repo contracts --issue 614
secpal-order resume contracts-614
```

Open the `contracts` tab. The command verifies the open GitHub issue and checks
that the fetched `main` matches the protected GitHub head. It creates a private
worktree and a local `issue/` topic branch. Use the same assignment name to
continue working.

Supported `--repo` values are `api`, `frontend`, `contracts`, `android`,
`deployment`, `.github`, `operations`, and `secpal.app`, all under `SecPal`.
A repository assignment needs no preview slot, database, or HTTPS route. The
repository's own validation determines which tools and services it needs.

## Private preview profiles

When validation needs an application or website preview, create a named workspace:

```bash
secpal-order new NAME --profile secpal
secpal-order new NAME --profile website
```

The `secpal` profile provisions API and frontend worktrees and a database behind
`https://NAME.preview.secpal.dev`. The `website` profile provisions the
`secpal.app` Astro preview.

## Workspace lifecycle

- `secpal-order status NAME` shows the assignment and its protected baseline.
- `secpal-order resume NAME` returns to the assigned workspace.
- `secpal-order stop NAME` frees preview capacity and preserves work. A
  repository-only assignment keeps its checkout and consumes no preview slot.
- `secpal-order start NAME` republishes a stopped preview. Use `resume` for a
  repository-only assignment.
- From the requesting Herdr workspace, run `secpal-order finish NAME` after
  required validation and protected GitHub delivery. It retains dirty work,
  unpublished commits, open PRs, and ignored local files. Review any ignored
  files before removing generated dependencies such as `node_modules`. A clean
  task that never changed its baseline can also be released.

Use local Codex on `840G11` for separately authorized infrastructure administration.

## Repository checks

Read the target checkout's `AGENTS.md`. For local checkouts, install the
repository's hooks with `./scripts/setup-pre-commit.sh` where available.
Run the smallest relevant checks while iterating and use the repository's
preflight for complete local validation when applicable. GitHub reviews,
required checks and protected merges govern delivery.

Repository-only tabs on `secpal.dev` include the development Node.js and
pre-commit tools and a private temporary directory for validation and signing.
For Contracts, run these commands in the assigned tab:

```bash
./scripts/setup-pre-commit.sh
npm run validate
git hook run pre-push -- origin "$(git remote get-url origin)" </dev/null
```

The setup script installs locked dependencies and checks the pre-commit hooks.
The host provides a Contracts pre-push hook for linked worktrees. Running the
hook directly executes the same preflight as a push without publishing a branch.

### API PHP validation

For API work, substitute your open issue number and assignment name:

```bash
secpal-order new php-2637-qualification --repo api --issue 2637
secpal-order resume php-2637-qualification
```

The assigned `api` tab puts assignment-specific `php` and `composer` launchers
on `PATH`. Both invoke the installed `secpal-order` PHP runner, which checks the
live Herdr tab and the registered SecPal API worktree.

For an existing `secpal` full-stack assignment, stop its preview before
repository-local validation. Resume the assignment and open its `api` tab.
If the shell lacks the launchers, including after a shell restart, load them
in that tab:

```bash
api_env=$(secpal-order php-env NAME) && eval "$api_env"
```

`command -v php composer` should resolve both commands under
`fullstack-previews/on-demand/api-bin`. The first locked install needs network
access for package downloads:

```bash
composer validate --strict
secpal-order php php-2637-qualification --online -- composer install \
  --no-interaction --no-progress --prefer-dist
composer check-platform-reqs
./scripts/setup-pre-commit.sh
```

Run the repository's complete preflight from the API tab. Git and Node run
in the tab, and the preflight inherits the launchers for its Composer and PHP
subprocesses, including the parallel and serial test suites:

```bash
PREFLIGHT_RUN_TESTS=1 ./scripts/preflight.sh
```

For focused runs, use commands such as `php artisan test --filter=ExampleTest`
or `vendor/bin/pint --test --dirty` in the API tab. Pint's PHP shebang
resolves the same launcher. Repository hooks and SSH signing run in the tab.
Inside the development image, PHP and its child processes have Composer and
ripgrep on `PATH` and inherit a 512 MiB CLI limit. The host-managed recipe
and installed image ID are recorded alongside `secpal-order`.

PHP commands use a disposable PostgreSQL 18 instance on a private internal
Podman network. The temporary test role can create test databases without
superuser rights. The instance has no published ports and is removed when the
command exits or is interrupted. Composer runs without a database. The explicit
`--online` option enables package downloads for Composer only.

Run one PHP command at a time in each assignment. Different assignments can run
independently. If the runner is killed before it can clean up, the next PHP
command, preview start or assignment finish retries its cleanup. A preview
start or assignment finish is rejected while PHP validation is active. Review
generated files before releasing the worktree.

### Android toolchain

Android Gradle work needs Java 21 and a discoverable Android SDK with
`adb` and `sdkmanager`. Set `ANDROID_SDK_ROOT` or `ANDROID_HOME` if the SDK is
outside `~/Android/Sdk`. Verify the toolchain with
`./scripts/check-system-requirements.sh --repo=android` from this repository.
