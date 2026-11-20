<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Polyscope PHP development image

The development image uses the official PHP 8.4 FPM/CLI image and a separately
pinned official Composer image. Git, Bash, Gettext, ripgrep, Python and the
application extensions support the existing workspace checks. The recipe uses
the API's signed SQLite package and hash-locked OpenTimestamps requirements.

Build in rootless Podman using the authenticated API source inputs. The
context is that revision's `docker/` directory.

```bash
export SECPAL_API_SOURCE=/absolute/path/to/authenticated/api-source
podman build --no-cache --format docker \
  --file "$PWD/containers/polyscope-php/Containerfile" \
  --tag localhost/secpal-polyscope-php:8.4 \
  "$SECPAL_API_SOURCE/docker"
```

Retain the source revision, build log, image digest and `apk info -v` inventory.
Verify the exact built image against the current vulnerability policy before
authorizing runtime use. The image uses UID/GID 1000 and the existing
`--userns=keep-id:uid=1000,gid=1000` mapping.

## Preview routing and runtime

The existing preview service groups independent rootless containers with Podman.
Nginx binds the existing preview port on loopback behind the authenticated edge.
Its image uses the official Nginx 1.30.7 OCI index with patched Alpine OpenSSL
and zlib packages. Build the gateway target from the same recipe:

```bash
podman build --no-cache --format docker --target preview-nginx \
  --file "$PWD/containers/polyscope-php/Containerfile" \
  --tag localhost/secpal-polyscope-nginx:1.30.7 \
  "$SECPAL_API_SOURCE/docker"
```

Nginx mounts only registered public document roots and private FastCGI sockets
read-only. Static SPA previews and canonical redirects continue through the same
hostnames. The build format retains the gateway and PHP-FPM health probes for Podman.

Each admitted API preview runs PHP-FPM in a dedicated container. It can read
only its own application worktree and write its runtime storage and socket
directory. Only PHP-FPM attaches to the existing preview database proxy
network. Both HTTP containers keep SELinux labeling, dropped capabilities
and read-only roots. The database proxy keeps its existing narrow Unix-socket
exception. API requests reach the fixed Laravel front controller. The preview
health probe checks loopback and the default 404. `/health/live` and
`/health/ready` remain application checks.

Nginx checks the admission marker at
`public/.polyscope-secpal-container-ready` on every API request and denies HTTP
access to dotfiles. Removing that marker withdraws the route immediately.
Registration and route refresh never issue admissions. The isolation guard
continues to exclude fenced workspaces.

## Live cutover

Use a separately authorized change window with the Polyscope runtime owner.
Record the existing unit, wrapper, image and route identities and the set of
authenticated, admitted API previews. Qualify the exact PHP and Nginx images
and load them under the local tags required by
`scripts/install-polyscope-container-preview.sh`.

Quiesce the existing preview service, database proxy and refresh path using
their user units. For each currently authorized, unfenced API workspace,
revalidate the native registration and its old root-level admission marker.
Place the marker in its real `public/` directory with the same ownership and
mode. Keep admissions withdrawn for all other workspaces.

Install the accepted source through the existing container-preview installer.
It rewrites the three command wrappers and the preview/proxy/refresh user units.
Verify authenticated routing, loopback and TLS boundaries, static content and
aliases, FastCGI socket ownership, API health, marker withdrawal, and the
current database isolation. Test an ordinary workspace and a fenced workspace.
Retain the previous files as rollback evidence and stop the affected units
if any of these checks fail.

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
python3 tests/run-polyscope-container-preview.py
python3 tests/render-polyscope-container-nginx.py
python3 -m unittest tests/polyscope-rollout-followups-unit.py
bash tests/polyscope-rollout.sh
```

Also qualify the actual image with a real linked Git worktree and dirty PHP
file, fresh Composer install, PHPStan, representative database tests, concurrent
workspaces and complete `All Checks`. Inspect test-role rights, database/schema
ownership, network isolation and cleanup. Run existing hooks and preflight.
Fixture tests alone do not establish real rootless compatibility.
