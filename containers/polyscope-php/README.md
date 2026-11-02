<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Polyscope PHP development image

`Containerfile` is the development toolchain definition. Its pinned official
FrankenPHP/PHP 8.4 base also preserves the binary used by container previews.
Composer comes from a separately pinned official image. Git, Bash, Gettext,
ripgrep and Python support existing API checks. The extension installer removes
its build dependencies.

Build as the existing unprivileged development account, from `SecPal/.github`.
Supply a protected-main API checkout for its existing hash-locked Python
requirements; no application source or second Python lockfile is copied.

```bash
export SECPAL_API_SOURCE=/absolute/path/to/your/api-workspace
podman build --no-cache \
  --file "$PWD/containers/polyscope-php/Containerfile" \
  --tag localhost/secpal-polyscope-api-toolchain:php84 \
  "$SECPAL_API_SOURCE/docker/python"
```

Base images and direct added packages are pinned. Retain the build log, image
digest and `apk info -v` inventory when qualifying a build. Missing packages
must fail the build, not select unpinned replacements. Missing host rootless
prerequisites are a boundary to report; do not install host packages or elevate.

The existing `scripts/install-polyscope-container-preview.sh` consumes this image
and installs PHP, Composer and `polyscope-api-test`. Updating an already running
preview remains separately authorized. An image build alone does not restart it.

## Workspace commands

Normal PHP commands retain the preview database path. PHP and Composer mount
only the current worktree and its actual shared Git metadata, including linked
worktrees. Shared SELinux volume labels (`:z`) support concurrent containers;
no wildcard Git trust, host ownership or SELinux-policy changes are needed.

From an API workspace:

```bash
composer install --no-interaction --prefer-dist
php vendor/bin/pint --dirty
php vendor/bin/phpstan analyse --no-progress
polyscope-api-test tests/Feature/AuthTest.php
polyscope-api-test --parallel --processes=2 tests/Feature/AuthTest.php
polyscope-api-test --full
```

The explicit test command creates a fresh PostgreSQL 18 container on an internal
Podman network without published ports. Generated credentials stay in private
temporary files and container environments. A container-local administrator
creates the `testing` role with `CREATEDB`, without superuser, role-administration
or replication privileges. The unchanged API bootstrap creates worker databases
and isolated schemas owned by that role.

Distinct resource identities isolate concurrent workspaces. Failure or
interruption removes test containers, the anonymous database volume, network
and credentials. Failed readiness stops the run; there is no preview fallback.

Container-backend provisioning generates `Pest` using this command and
`All Checks` using full mode followed by Pint and PHPStan. Full mode executes
the existing API `composer test`: parallel tests excluding the serial group,
then serial tests. Focused mode passes arguments directly to `php artisan test`.
The normal PHP wrapper does not interpret commands. Non-container actions and
preview routes remain unchanged.

## Qualification

```bash
python3 tests/run-polyscope-api-tests.py
python3 tests/install-polyscope-container-preview.py
python3 -m unittest tests/polyscope-rollout-followups-unit.py
bash tests/polyscope-rollout.sh
```

Also qualify the actual image with a real linked Git worktree and dirty PHP
file, fresh Composer install, PHPStan, representative database tests, concurrent
workspaces and complete `All Checks`. Inspect test-role rights, database/schema
ownership, network isolation and cleanup. Run existing hooks and preflight.
Fixture tests alone do not establish real rootless compatibility.
