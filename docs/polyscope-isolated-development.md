<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Isolated Polyscope development

This source change separates native workspace registration from setup and runtime
activation for the already authorized `SecPal/api#2639` task. Polyscope remains the
only workspace registry; `secpal-polyscope-workspace.py` remains the coordinator.
The reservation is a single immutable before-ID fence, not another registry.

## Source and operating boundaries

The guard qualifies Polyscope 0.29.0 by its executable digest and the native
repository/group contract. A different binary, missing authority, changed linked
repositories, ambiguous identity or incomplete new group fails closed. Requalify
the native contract before changing the executable pin.

A protected source merge is required before installation. Install only a reviewed,
SSH-signature-verified, immutable commit from protected main, and record its commit,
tree, executable and installed-file digests. Do not install this document's
examples or a qualification harness as an alternative execution authority.

Source tests do not authorize live installation, restarting services or creating
the actual API workspace. Two separate operating gates remain open: successful
bounded quiescence of all old provisioning/refresh processes, and repair and
qualification of the existing global preview renderer. A missing preview route
must not trigger automatic re-provisioning.

## Reservation and execution admission

Before any native creation, an administrator arms
`/etc/secpal/workspace-isolation.json` using the versioned guard's `--arm --model`
operation. It accepts only the fixed API issue, the qualified executable, an empty
creation fence and a non-Claude model. It publishes complete, root-owned authority
atomically and exclusively; an existing reservation is never overwritten. The
coordinator reads the same reservation and rejects another task's reservation
before dispatching API#2639 creation.

The required marker `/etc/secpal/workspace-isolation.required` makes loss of the
policy fail closed. Once armed, the default authority also applies when a service
loses its optional environment file. Every effective native repository/workspace
setup and run command must be wrapped before opening the creation window,
including commands inherited by the three linked repositories. Wrapping joins the
entire setup sequence inside one guard; it does not merely disable autostart.

The guard uses the existing coordinator's native observation and shared creation
fence. It blocks the target root, all children and new incomplete/unbound related
workspaces from their earliest registration. An interrupted coordinator leaves its
pending fence intact until native read-back reconciles the outcome. Repetition
adopts that group; it must not create a replacement. Existing workspaces and later
complete, independently bound groups keep regular admission.

Rollout, worktree bootstrap and runtime creation reject protected paths before
setup or readiness checks. Runtime reconciliation preserves their identities
rather than pruning them. While a reservation is active, orphan preview-database
collection is deferred; reconcile that housekeeping separately after the
reservation's lifetime. Preview rendering excludes protected members even if they
contain old readiness tokens. Cleanup and refresh must not remove their files or
restart preview services solely because they were registered.

A bounded observation releases its shared lock before executing an admitted
command. Long-lived ordinary workers must not pin the creation fence.

## Narrow filesystem grant and runner

Only after native read-back proves exactly the expected root and linked group may
an administrator prepare the API root. The other three repositories receive no
grant. Audit the source tree, split every multiply-linked regular inode atomically,
preserve content/ownership/mode/extended attributes, and run Git fsck. Reject shared
Git stores, external symlinks, nested mounts, special files, set-ID/capability
files, mixed ownership and known credential filenames.

The administrator creates one root-controlled idmapped bind view with
`nosuid,nodev`, mapping source UID/GID 1003 to 1001 for this tree only. Preserve
SELinux Enforcing and apply the existing container-file labeling contract solely
to the new authorized tree. Do not relabel the clone root, grant parent ACLs or
recursively change ownership. If this mount/label contract fails, stop.

The root-owned development receipt records the native repository, issue,
workspace ID, canonical path, branch, four-member group and source device/inode/
UID/GID. It also pins the view inode and toolchain/PostgreSQL image IDs, an empty
root-owned OCI hooks directory and a root-owned containers configuration. It is a
receipt of a native association, not an independently editable workspace mapping.

The fixed CLI accepts `exec -- command...`, `test -- command...`, `build` and
`cleanup`. It accepts no host mount, privilege, task selector or workspace path.
Before execution it refreshes the exact existing read-only coordinator resolve,
checks the complete native identity and filesystem binding, then audits the view.
A replacement native directory at the same path is rejected. Development commits
can change HEAD without changing the authorized branch or group.

All OCI execution uses UID 1001's explicit local storage/runroot, empty hooks and
clean environment. It grants no Polyscope management token, secpal socket or host
credential. PHP 8.4, Composer, Git and Podman's Buildah backend remain available.
Tests get a private PostgreSQL 18 instance, fresh credentials, volume and internal
network. Resource intent is recorded before creation so interrupted clients cannot
lose cleanup ownership; credential cleanup runs even if OCI removal fails.
SIGKILL requires explicit scope-labeled cleanup, which needs no management API.

The launcher is not the Unix access-control boundary: UID 1001 already controls
its own rootless OCI account. The narrow mount and host DAC/SELinux/network rules
are that boundary. Revocation therefore requires retiring the grant and any
processes holding it, not just deleting a receipt. Never add broad sudo, secpal
execution or management access to make the launcher work.

## Separate activation and rollback order

The following is an ordering contract, not a live activation approval:

1. Verify protected source/signatures, backups, installed hashes, native groups,
   all persistent container IDs/start times, service PIDs/start times and prior
   qualification evidence. Record active jobs, cgroups and creation locks.
2. Close all native creation entrances, including UI/WebSocket/REST and relay RPC.
   A coordinator lock alone does not close the other entrances. Confirm the
   qualified native relay-disable behavior and controlled local management access.
3. Pause only the documented provisioning/path/timer/refresh triggers. Let old
   processes drain successfully within a bounded window; require empty jobs and
   cgroups and released locks. On timeout, failure or unexplained work, abort.
   Do not force-kill old live services.
4. Install the pinned guard/coordinator/dependencies and wrapper-capable sources;
   preserve every existing restricted-sudo and management-network denial. Existing
   installers can restart services: their invocation needs separate authorization.
5. Under the closed creation window, make required authority effective, arm the
   reservation through the existing coordinator and wrap every effective setup/run
   source. Verify both positive ordinary-workspace and negative target admission.
6. Reopen only the controlled native interface needed for one trusted coordinator
   creation. Authenticate the returned root and all children before any writable
   grant. Keep the guard effective through every later timer/watcher/refresh.
7. Separate approval for actual creation and live activation remains necessary.
   Recheck all persistent services, containers and evidence after each phase.

On an uncertain creation result, retain the reservation and pending fence and use
native read-back before retrying. Do not delete database rows or invent IDs.
Rollback must first close creation and quiesce the changed execution paths, revoke
only the new view and retire only its scoped disposable resources, then reconcile
any new group through the native interface. Restore only known safe source and
configuration snapshots. Keep deny guards effective while a protected group
exists; restoring an old unguarded provisioner could activate it. Never restore the
previous arbitrary coordinator execution or direct management access for codex.

## Regression entry points

Run `bash tests/polyscope-rollout.sh`, `python3 tests/secpal-polyscope-workspace.py`
and `python3 tests/install-polyscope-container-preview.py`, followed by the complete
`bash scripts/preflight.sh`. The rollout suite includes the portable guard,
interruption, reservation-scope and launcher identity tests. Administrative atomic
publication tests use `tests/polyscope-isolation-publication.py` with
`SECPAL_PUBLICATION_TEST_ROOT` set to a disposable root-owned directory.

Native and kernel qualification additionally needs a separate Polyscope data and
clone root, authentic issue metadata, private service namespaces, four disposable
repository members, UID 1001's own pinned images and one disposable idmapped view.
Exercise native registration, ordinary admission, path/timer reconciliation,
preview refresh, post-registration crash/adoption, filesystem replacement,
hardlink/symlink/nested-mount rejection, actual SELinux decisions, PHP/PostgreSQL/
OCI tasks, SIGTERM/SIGKILL and repeated scope cleanup. Delete only those native
fixture registrations and fixture resources during rollback. Keep exact source
tree/file digests and results outside the repository; never commit host reports,
credentials or concrete live grants.
