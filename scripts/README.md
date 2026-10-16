<!--
SPDX-FileCopyrightText: 2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

## Read-Only WorkGraph Planning

`secpal-work-graph.py` reads native GitHub parent/sub-issue and dependency
relationships. Commands `show`, `ready`, `next`, `validate` and
`validate-issue` report scope, readiness, selection and malformed input without
writing issues or PRs. See [planning semantics](../docs/work-graph-contract.md).

```bash
python3 scripts/secpal-work-graph.py show SecPal/.github#1032
python3 scripts/secpal-work-graph.py ready SecPal/.github#1032
```

`secpal-work-graph-audit.py` provides an optional read-only closure audit using
native relationships. Its default inventory covers all eight active SecPal
repositories, including private `SecPal/operations`; the authenticated reader
needs access to that repository. Use `--repo` to select an explicit scope. An
unreadable repository is reported as unavailable rather than silently skipped.
Neither reader grants PR or merge authority.

## Validation Scripts

### `secpal-dependabot-manifest-coverage.mjs`

Deterministically discovers tracked dependency manifests and validates either
the shared `MANIFEST_COVERAGE` assertion or the separate `CADENCE_POLICY`
assertion. Ecosystem knowledge and upstream provenance come exclusively from
`policies/dependabot-manifest-catalog-v1.json`. Exact repository exceptions and
module classifications are usable only from a separately supplied trusted
protected-history root; subject-branch review strings are never authority.

```bash
node scripts/secpal-dependabot-manifest-coverage.mjs coverage \
  --repository SecPal/example --default-branch main \
  --trusted-policy-root /path/to/protected-baseline --format json
node scripts/secpal-dependabot-manifest-coverage.mjs cadence \
  --repository SecPal/example --format text
```

See
[`docs/dependabot-manifest-coverage.md`](../docs/dependabot-manifest-coverage.md)
for discovery, anti-drift, matching, exception, reporting, and reusable-workflow
semantics.

### `check-domains.sh`

Enforces the SecPal `secpal.*` namespace by classification. The script greps text files
in the working tree (via `grep -r --include=...`, so untracked files matching
the include patterns are inspected too), extracts each matching hostname-like
token independently, and flags tokens that fall outside the approved set
of public/external hosts (`secpal.app`, `apk.secpal.app`, `secpal.io`),
development/preview hosts (`secpal.dev`, `api.secpal.dev`, `app.secpal.dev`, the
`preview.secpal.dev` base, plus arbitrary `*.preview.secpal.dev` previews), the
identifier-only `io.secpal.*` reverse-DNS namespace,
and the exact private internal logical database service identity
`db.secpal.internal`. It also surfaces
`api.secpal.app`, the deprecated `.app` web host, so callers cannot reintroduce
it as an active host.

The `io.secpal.*` allowance applies in explicit reverse-DNS identifier
contexts such as an application ID, package, namespace, or bundle identifier.
[ADR-026](../docs/adr/20261002-client-trust-offline-recovery-adr026.md) also
authorizes the exact application identities `app.secpal.libre` and `io.secpal.dpc`
as complete Markdown inline code spans. These exceptions require every occurrence
on the line to be classified and do not approve URLs, public hosts, arbitrary
suffixes, or inline-code syntax in executable files. The Android ID
`app.secpal` remains a valid architecture value, but it is outside this
scanner's intentionally `secpal.*`-seeded matcher and is not claimed as an
enforced value here.

`db.secpal.internal` is an approved logical PostgreSQL connection/TLS service
identity, not a public web host or DNS-routing commitment. This exact allowance
does **not** approve arbitrary `*.secpal[.]internal` names; all other
`secpal[.]internal` identities remain fail-closed unless a separate explicit
architecture decision adds one.

**Active namespace policy versus historical evidence:**

- Every `secpal.*` token on an active/current policy surface is classified
  independently and fail-closed. An approved token on the same source line
  cannot mask a forbidden token.
- The validator's small exact-path historical-evidence registry permits only
  proven archived/superseded records to quote historical identifiers. It is not
  a wildcard path rule, a documentation/ADR exemption, or domain approval;
  placing the same identifier in an ordinary current file still fails.
- Regression fixtures that need forbidden values construct their final token at
  runtime. This keeps the tracked test source subject to the active scanner
  while ensuring temporary fixtures exercise the real complete value.

**Scope (intentional limit):**

- The match regex is `secpal\.[A-Za-z0-9.-]+`, so only `secpal.*` strings are
  ever inspected. Non-`secpal` domains are out of scope by design — even when
  they belong to SecPal. The historical `guardguide.de` fixture still proves
  that matcher boundary.
- Non-`secpal` hosts need their own policy guards; the historical
  `guardguide.de` example from SecPal/.github#483 supplies no live repository
  membership. Such hosts
  are not first-class entries here. Adding them to this allowlist would be
  inert because the matcher never sees them.
- Treat the banner's "Forbidden" list as "forbidden `secpal.*` variants",
  not "every non-SecPal domain on the internet".
- The scan protects the gitignored agent scratch directory `.context/` with
  two complementary layers (SecPal/.github#489). Layer one is the
  **grep exclusion** `--exclude-dir=".context"`, which skips every directory
  named exactly `.context/` at any depth (alongside `.git/`, `node_modules/`,
  and `vendor/`). Polyscope-managed workspaces use `.context/` to pass
  throwaway files between agents and the `gh` CLI (PR body drafts, scratch
  notes, etc.) that never reach CI, so the local gate must not flag them
  either. Layer two is the **tracking-aware guard**: before grep runs, the
  script invokes `git ls-files` on `.context/` and exits non-zero if any
  path under `.context/` is actually tracked by git. Because `--exclude-dir`
  is git-tracking-unaware, this guard closes the `git add --force` bypass
  review flagged on this PR — force-tracked `.context/` files would
  otherwise be visible to CI but silently ignored locally. The guard is a
  no-op outside a git working tree (e.g. in the throwaway `mktemp`
  workspaces the regression tests use), so it does not interfere with
  packaging or distribution scenarios. Violations in any tracked path
  (inside or outside `.context/`) still fail the gate.

**Usage:**

```bash
bash scripts/check-domains.sh
```

**Exit Codes:**

- `0`: No forbidden `secpal.*` variants or deprecated `.app` web-host usages
- `1`: One or more violations found

### `audit-closed-epics.sh`

Legacy migration-compatibility helper that compares Epic checklist mirrors with
current issue state. It is report-only; the canonical resolver and GitHub-native
relationships remain authoritative.

**Usage:**

```bash
# Audit the full SecPal workspace set
bash scripts/audit-closed-epics.sh

# Audit a smaller scope
bash scripts/audit-closed-epics.sh --org SecPal --repo .github --repo api
```

**What It Checks:**

1. Searches for open and closed Epic issues by label and title
2. Parses checklist-linked child issues from each epic body
3. Ignores PR references so merged PR numbers are not mistaken for issues
4. Reports:
   - open child issues in closed epics
   - checked items that point to non-closed issues
   - stale unchecked checklist items whose child issues are already closed

**Exit Codes:**

- `0`: No checklist issues found
- `1`: One or more checklist issues found
- `2`: Usage or dependency error

### `check-system-requirements.sh`

Validates the local toolchain baseline for the managed SecPal repositories,
including the Android-specific Java/SDK requirements that direct Gradle and
Polyscope-provisioned workspaces need.

**Usage:**

```bash
bash scripts/check-system-requirements.sh
bash scripts/check-system-requirements.sh --repo=android
```

**What It Checks For Android:**

1. Node.js 26 (Current) and `npm`
2. Java 21 plus `javac`
3. Android command-line tools via `sdkmanager`
4. Android platform-tools via `adb`
5. An SDK path under `$HOME/Android/Sdk` or via `ANDROID_SDK_ROOT` / `ANDROID_HOME`
6. Android local dependencies such as TypeScript, Vite, Vitest, and ESLint
7. Presence of the committed native `android/` project directory

**Exit Codes:**

- `0`: All critical requirements met
- `1`: One or more critical requirements missing

### `check-openapi-verified-endpoints.mjs`

Regression guard that fails if `docs/openapi.yaml` in any SecPal repo omits an
operation from the verified-endpoint allowlist. The allowlist is defined inside
the script and reflects operations that have confirmed feature-test coverage.

**Usage:**

```bash
node scripts/check-openapi-verified-endpoints.mjs <path-to-openapi.yaml>
```

**Exit Codes:**

- `0`: All required operations are present
- `1`: One or more required operations are missing
- `2`: Usage or file-read error

### `validate-ai-instructions.sh`

Validates the independent `AGENTS.md` runtime baseline, Copilot review profile,
and focused instruction overlays across all repositories.

**Usage:**

```bash
# In any repository (.github, api, frontend, contracts)
./scripts/validate-ai-instructions.sh
```

**Tests Performed:**

1. **File Existence**

   - Checks for `AGENTS.md`
   - Checks for the independent `.github/copilot-instructions.md` review profile

2. **REUSE Compliance**

   - Validates `AGENTS.md` REUSE metadata
   - Requires the complete repository-policy expression in inline SPDX
     metadata or a valid `.license` sidecar and rejects conflicting or duplicate
     declarations across both sources
   - Requires plain `AGPL-3.0-or-later` for managed baselines and preserves only
     the API repository's intentional `CC0-1.0` baseline
   - Preserves exact deliberate `AGPL-3.0-or-later`, `Apache-2.0`, `CC0-1.0`,
     or `MIT` expressions on focused overlays
   - Rejects the obsolete expression
     `AGPL-3.0-or-later AND LicenseRef-SecPal-Attribution`

3. **Markdown Linting**

   - Runs markdownlint-cli on instructions
   - Uses the repo-pinned `markdownlint-cli` installed by `npm ci`
   - Does not download a fallback tool

4. **UTF-8 Markdown Structure**

   - Rejects unreadable, empty, malformed UTF-8, or heading-less files

5. **Focused Overlay Structure**

   - Requires opening and closing frontmatter delimiters
   - Requires non-empty `name` and `applyTo` values

6. **Discovery Size**
   - Ensures `AGENTS.md` stays below the 32 KiB runtime discovery ceiling

The validator does not require textual equality, mirror declarations, copied
overlay bodies, inheritance markers, or arbitrary policy keywords.

**Exit Codes:**

- `0`: All tests passed
- `1`: One or more tests failed

**Example Output:**

```
=========================================
SecPal AI Instructions Validation
=========================================

Repository Type: api

✓ required instruction files exist
✓ AGENTS.md is readable UTF-8 Markdown
✓ copilot-instructions.md is readable UTF-8 Markdown
✓ AGENTS.md has REUSE license
✓ copilot-instructions.md has REUSE license
✓ instruction Markdown passes lint
✓ instruction overlays include valid frontmatter
✓ AGENTS.md stays under runtime discovery size limit

=========================================
Summary
=========================================
Total Tests: 8
Passed: 8
Failed: 0

✓ All tests passed!
```

**CI Integration:**

Automatically runs in GitHub Actions:

- On push to `main` (when instruction files change)
- On pull requests (when instruction files change)
- Manual trigger via `workflow_dispatch`

See `.github/workflows/validate-ai-instructions.yml`

**Dependencies:**

- `bash` (required)
- `grep` (required)
- `npm ci` in `SecPal/.github` (installs the pinned `markdownlint-cli` and `prettier` CLIs)
- `ruby` (optional, only for the legacy YAML syntax check)

**Repository Identity:**

Canonical GitHub and Polyscope callers supply trusted repository identity via
`GITHUB_REPOSITORY` or `SECPAL_REPOSITORY_NAME`. Content-based detection remains
a local compatibility fallback and does not select production policy when a
trusted identity is available. Repository-path mode clears ambient identity and
derives each target independently. The legacy `REPO_TYPE` hint cannot select
the strict API policy without the exact `secpal/api` manifest:

- **org**: `.github` repository (org-wide instructions)
- **api**: SecPal API (has Composer package name `secpal/api`)
- **frontend**: React frontend or Android wrapper (has `package.json` with `vite`)
- **website**: Astro landing page (has `astro.config.mjs`)
- **contracts**: OpenAPI contracts (has `package.json` with `openapi` or `docs/openapi.yaml`)

### `sync-required-checks.sh`

Builds and applies the repository-specific required status-check payloads for
the SecPal application repositories.

**Usage:**

```bash
# Inspect the payload for one repository without writing to GitHub
bash scripts/sync-required-checks.sh --repo secpal.app --print-payload | jq

# Apply the configured payload to one repository
bash scripts/sync-required-checks.sh --repo api --apply

# Apply the configured payloads to every managed repository
bash scripts/sync-required-checks.sh --apply
```

**Managed Repositories:**

- `.github`
- `api`
- `frontend`
- `contracts`
- `deployment`
- `android`
- `secpal.app`

Private `operations` retains its separately owned protection and is outside
this public required-check inventory. Deployment's five existing checks remain
bound to GitHub Actions App `15368`. The review-baseline mode retains its
original six-repository scope and does not manage Deployment's review settings.

**What It Does:**

1. Defines the required status-check contexts per repository in one manifest
2. Builds the exact JSON payload GitHub expects for branch protection updates
3. Applies the payload through `gh api` using `--input` so booleans and arrays stay typed correctly
4. Keeps the live branch-protection baseline repeatable after workflow or context drift
5. Emits `strict: true` while preserving each managed repository's required
   checks and App bindings. Pull request branches must be up to date with
   protected `main` before merging.

**Exit Codes:**

- `0`: Payload printed or sync applied successfully
- `2`: Usage error, unknown repository, or missing dependency

### `audit-polyscope-state.py`

Audits the local Polyscope runtime state for repository/clone drift, stale
worktree directories, clone-local config hygiene, and over-retained SQLite
backups.

**Usage:**

```bash
# Audit the real local Polyscope state
python3 scripts/audit-polyscope-state.py

# Audit a custom Polyscope home and print JSON findings
python3 scripts/audit-polyscope-state.py --polyscope-home /tmp/test-polyscope --json
```

**What It Checks:**

1. Repository IDs in `polyscope.db` that do not have a matching clone root
2. Clone roots that no longer belong to any registered repository
3. Clone subdirectories that are not valid Git worktrees
4. Valid Git worktrees that are not registered in the `worktrees` table
5. Registered worktrees whose on-disk path no longer exists
6. Worktree rows referencing a `repo_id` that is missing from `repositories`
7. Registered worktrees missing clone-local `polyscope.local.json`, drifting from the repo-root config, or where Git would still track `polyscope.local.json` (the check uses `git check-ignore` so commented (`#`), negated (`!`), or look-alike (`.bak`) entries in `info/exclude` are not mistaken for effective coverage, and per-worktree gitdirs of linked worktrees are followed automatically)
8. `polyscope.db.backup-*` files beyond the configured retention count

**Exit Codes:**

- `0`: No findings
- `1`: One or more findings detected
- `2`: Usage error or missing dependency/state

### `reap-polyscope-clones.py`

Conservatively reclaims orphaned Polyscope repository clone roots and
unregistered worktree directories. It protects every repository root and every
active `worktrees.path` currently registered in `polyscope.db`, waits seven days
by default, and skips candidates with lock files or active processes. An active
worktree at a clone-root level is never scanned for children; otherwise, only
its immediate non-hidden child directories can be worktree candidates.
Immediately before deletion the reaper revalidates the database while holding a
write-reservation transaction and atomically detaches the candidate through a
pinned, non-symlink parent-directory handle, so concurrent registration or a
parent-path replacement cannot redirect recursive deletion. Quarantines live at
the clone-root level so a later run can finish cleanup after an interruption.
The reaper revalidates candidates after process inspection before measuring
dry-run storage, and rejects symlinks and paths outside the configured clone
root.

**Usage:**

```bash
# Inspect eligible orphan roots and potential reclaimed space
python3 scripts/reap-polyscope-clones.py --dry-run

# Reap an isolated fixture or non-default Polyscope location
python3 scripts/reap-polyscope-clones.py --polyscope-home /tmp/polyscope --clone-root /tmp/polyscope/clones --grace-period 14d
```

The rollout installer enables `polyscope-clone-reaper.timer`, which runs the
reaper daily after startup. The reaper prints reclaimed bytes and supports
`--json` for operational reporting.

### `secpal-polyscope-workspace.py`

The existing trusted coordinator uses `ensure --repo SecPal/<repo> --issue <n>`
before dispatching an already authorized delivery. It reuses an exact active
workspace, including pending source/evidence, or creates one through native
Polyscope. No additional NEW approval is required. The native workspace ID
returned by read-back is used for subsequent `exec --workspace-id <id>` calls.
Issue-bound `exec` without an ID performs this setup automatically. Native
creation supports an issue or a PR binding; combined selectors require an existing
exact native mapping and fail before creation when that capability is unavailable.
A new issue-only workspace cannot pin a SHA through the native API; this
combination is rejected before creation. Existing workspaces can be SHA-checked.

`resolve` never writes. Plan-only sessions use read-only resolution; setup belongs
to the trusted coordinator outside that sandbox. Unknown, paused, shared or
mismatched ownership is a technical blocker, never permission to replace or reset
a workspace. Native issue self-assignment retains its existing authority.

The system installer maintains the existing `/usr/local/bin/secpal-polyscope-workspace`
entry and WebSocket bridge; the user installer also exposes the same source in
its bin directory. No new credentials, daemon, workspace registry or cleanup
authority are introduced. The read-only WorkGraph resolver is consumed from the
existing registered governance checkout. The existing `POLYSCOPE_HOME`,
`POLYSCOPE_CLONE_ROOT` and `POLYSCOPE_API_BASE` settings are consumed directly;
the API/bridge remains restricted to the configured loopback origin. Dispatch
retains the existing managed Git wrapper through `POLYSCOPE_GIT_BIN_DIR`. Issue
and PR metadata reach the bridge through stdin, never process arguments.

A serialized create uses a durable in-flight fence in its lock file. After a
lost/ambiguous response, native registration must establish the outcome before
another create; do not delete the fence or retry blindly. Pending setup failures
remain explicit technical blockers until native read-back establishes a usable
workspace. A repository-scoped native rejection and independent absence read-back
clear only that failed attempt, allowing a later corrected request. No existing workspace is deleted or modified to recover setup.

### `install-polyscope-rollout.sh`

Installs the unprivileged SecPal Polyscope rollout systemd units that keep
registered workspace clones, prompts, and preview config in sync. Run this
from the workspace root when `setup-hooks.sh` reports a managed repo as
**skipped (missing directory)** so the rollout-managed workspace can sync back
to the expected repository set.

**Usage:**

```bash
POLYSCOPE_SERVER_SCOPE=system bash .github/scripts/install-polyscope-rollout.sh
```

Run `install-polyscope-system-components.sh` first. This installer remains
unprivileged, requires the invoking account to be `secpal`, and verifies the
exact fixed-helper capability:

`sudo -k -n /usr/local/libexec/secpal-polyscope-nginx-apply --check`

The credential reset ensures the check proves the exact `NOPASSWD` rule rather
than a cached interactive sudo timestamp. It never tests generic sudo access,
rejects helper-path overrides, and exits before writing user units when the
fixed helper, fixed manifest path, system server drop-in, or exact
authorization is unavailable. The helper check validates the installed
root-owned bundle independently of the current manifest and advertises
`manifest_schema=3`; the unprivileged producer refuses to publish unless that
capability is present on the same fixed helper used for activation. Schema 3
binds the reduced three-repository preview inventory. Older schema-1/2 manifests
and mismatched installed renderers fail closed; update the root-owned consumer
bundle before publishing the new producer manifest.
Environment-selected helper paths cannot authorize publication. This permits
consumer-first schema upgrades and allows a malformed active manifest to be
replaced without leaving Nginx on an unreadable manifest. Both system- and
user-scope server startup hooks skip repository config and database
synchronization; they perform only the Nginx convergence needed before the
service reports ready. If the full provisioner already holds the shared lock,
the startup hook exits successfully because that in-flight provisioner performs
the same final Nginx convergence. User-scope startup also receives the exact
sudo binary validated by the installer. Startup and routine refreshes use the
same configured clone root and provision lock as the full provisioner. A
system-scope installation accepts only the exact reviewed nonblocking startup
hook from the privileged component installer. Routine instruction/config
synchronization refreshes Nginx without reprovisioning every worktree;
provisioning remains owned by its path/timer service. The path unit deliberately
ignores the broad SQLite WAL stream so ordinary Polyscope activity cannot create
a provisioning loop; the main database, generated configs, and periodic timer
remain convergence inputs.

`--source-script` accepts a custom rollout implementation only as part of a
complete source bundle: the script must be executable, have the constrained
`polyscope_nginx.py` library and executable nginx helper beside it, and have an
executable `validate-ai-instructions.sh` sibling plus the canonical js-yaml
verifier with the committed npm validator dependencies installed. The installer
loads the pinned parser and verifies its required API before any installation
writes, then watches the runtime files and npm lock state for rollout changes
and dependency-install recovery.

After installation, the user-level `polyscope-rollout-sync.service` and
`polyscope-worktree-provision.service` units take care of provisioning new
managed repositories automatically when the canonical repo list changes. Both
the provision path and the three-minute fallback timer are enabled. The
provisioner reads only active `worktrees` registrations from `polyscope.db`,
resolves them beneath the matching repository clone root, and never scans an
unregistered clone as a setup candidate. The physical hash directory remains
the database's authoritative deletion path. Stable aliases are direct sibling
symlinks recorded in a strict per-repository registry; after official deletion
removes the physical path and registration, the next database-triggered
reconciliation removes only those recorded broken aliases.

On the canonical host, `--provision-worktrees` execution always includes Nginx
refresh even when an older installed unit does not yet contain
`--refresh-nginx`. Registered API previews receive two managed user services,
one scheduler and one combined queue worker. The services inherit the
installer-controlled tool `PATH`, resolve database credentials at process start
through the rollout wrapper, restart on failure, disappear when their worktree
registration is removed, and must produce a scheduler heartbeat before new
preview access is granted. Failed runtime-owner activation or heartbeat checks
revoke any access retained from an earlier successful provision. Stale services
for removed registrations are still pruned when another worktree fails canonical
instruction or routine ACL reconciliation. They are also restarted when the
worktree revision, dirty tracked code, untracked source metadata, or
source/worktree environment metadata changes. The corresponding Polyscope run
actions remain available for explicit diagnostics and do not autostart while
the managed services own the runtime. Noncanonical clone-root or database
installations instead keep those actions autostarted because no persistent
systemd owner is managed there. A failed reconciliation preserves existing units
only for still-registered physical worktrees; units belonging to removed
registrations remain eligible for pruning. Stale unit files are removed only
after systemd confirms that their services stopped successfully; a failure
preserves that unit without blocking later independent stale-unit cleanup.
Desired unit names are validated before cleanup starts, unreadable contents plus
ownership or permission drift are replaced, and independent cleanup and
activation failures are reported together. Routine preview ACL reconciliation
likewise attempts every unregistered physical worktree before reporting any
individual denial or repository-integrity failures. The paired daily
`polyscope-clone-reaper.timer` removes only aged orphan clone roots after checking
the live database allowlist, locks, and processes.

Every generated repository setup sequence starts with the validation-only
`--validate-instruction-worktree` command and explicit repository name inside
one strict shell entry. Cached setup definitions without that identity argument
remain compatible during rollout convergence by resolving the repository from
the worktree's active Polyscope database registration. The installed user
service exports the configured workspace root to those cached commands, so
nondefault installations retain the same managed-source identity boundary.
Missing, ambiguous, and unmanaged registrations fail closed instead of trusting
ambient identity or
mutable worktree manifests. The entry groups the complete native setup with
fail-fast semantics, so validation or any later command failure prevents every
remaining npm, Composer, `.env`, database, migration, seed, build, or repository
setup command. The external provisioner applies the same canonical contract
before its local configuration, hook, alias, setup, and marker writes.

The worktree provision service waits three seconds before each activation to
coalesce SQLite event bursts and takes a process-shared lock before provisioning.
Its 15-minute start budget leaves the provisioner time to record scheduler
readiness failures and perform final ACL/runtime cleanup before systemd ends the
oneshot.
The path and fallback timer both target that serialized service. Five starts per
ten seconds cannot be exhausted by the three-second activations, while genuine
service failures remain visible. A deliberate user-installer convergence clears
only historical failed state for the provision path and service before enabling
the new unit contract; it does not hide later failures.

### `install-polyscope-system-components.sh`

Installs only the root-owned Polyscope system boundary: the constrained nginx
helper and renderer bundle, two exact sudoers command forms, and the system
Polyscope server drop-in. Review the script, then run it interactively:

```bash
sudo -k
sudo .github/scripts/install-polyscope-system-components.sh
```

The host must provide `/usr/bin/setfacl` from its `acl` package before
activation. The installer checks this prerequisite before writing any system
component and exits with an actionable error when it is unavailable.

The installer resolves `node` before writing the system drop-in, verifies that
the `secpal` service account can execute it, and adds its directory to the
service `PATH`. If root's environment cannot discover a user-managed Node.js
installation, pass its absolute path explicitly:

```bash
sudo .github/scripts/install-polyscope-system-components.sh \
  --node-bin /home/secpal/.local/share/node/bin/node
```

The administrator enters the password only at the terminal prompt. The script
validates sudoers syntax before activation, writes fixed root-owned targets
atomically, and restores the previous components if activation fails. It does
not authorize shells, Python, `systemctl`, file utilities, or user-selected
paths through passwordless sudo.

`DESTDIR=/path scripts/install-polyscope-system-components.sh --stage-only`
renders a deterministic packaging fixture without root or a local `secpal`
account. Its UID 1000 systemd value is for validation only; a real installation
always resolves the target host's `secpal` UID and an executable Node.js path
before activation. Packaging tests may pass `--node-bin` to render the intended
service `PATH` without inspecting the target account.

Before activation, the installer verifies the executable canonical rollout and
validator source bundle, committed lockfile, and installed pinned Markdown and
YAML dependencies under `/home/secpal/code/SecPal/.github/`. The parser must
resolve and expose the required loading API to the `secpal` service account.
The system drop-in executes that source directly, so a fresh installation does
not depend on the user-local rollout link created during the following
unprivileged installation step.

The installed `/usr/local/libexec/secpal-polyscope-nginx-apply` accepts only no
arguments (apply) or `--check` (non-mutating boundary check). It reads the fixed
mode-`0600`, `secpal`-owned JSON manifest, rejects links, unsafe ownership,
unknown fields, non-loopback upstreams, invalid ports, and unsafe repository
identifiers, then renders one fixed nginx target internally. The exact
root-owned manifest library is checked before it is imported. Activation is
atomic; `nginx -t` precedes reload, and validation or reload failure restores
the prior configuration. Root may invoke the helper directly; invocations
carrying sudo identity are accepted only from `secpal` with its exact UID.

When the managed repository set changes, rerun this privileged installer before
the unprivileged rollout installer to replace the root-owned renderer contract.
During a staged upgrade, an older installed renderer can retain a syntactic
route for a retired repository. The live rollout supplies only the exact fixed
tombstone required by that older contract and fails closed if the tombstone's
clone-root path exists, so the compatibility route cannot serve content. The
privileged reinstall removes the obsolete content mapping from generated nginx
configuration. The retired hostname prefix remains reserved solely as an
explicit `404` boundary so it cannot be reinterpreted as a generic workspace.

After both installation steps, verify the steady state:

```bash
sudo -k -n /usr/local/libexec/secpal-polyscope-nginx-apply --check
systemctl --user is-active polyscope-rollout-sync.path
systemctl --user is-active polyscope-worktree-provision.path
systemctl --user is-active polyscope-worktree-provision.timer
systemctl --user is-active polyscope-clone-reaper.timer
```

### `setup-hooks.sh`

Installs pre-commit and commit-msg hooks across every managed SecPal repo
discovered next to the `.github` checkout. It also retires legacy
SecPal-managed full-preflight `pre-push` symlinks without touching custom hooks.

**Behavior:**

- Repos that are **missing on disk** are surfaced as a soft warning (separate
  summary line) and the script still exits `0` when every other repo's hooks
  installed cleanly. Run `.github/scripts/install-polyscope-rollout.sh` (or
  sync via Polyscope) to recover the rollout-managed workspace state.
- Managed repo paths that exist but are **not directories** are treated as real
  failures because they indicate a corrupted workspace layout, not a repo that
  simply has not been synced yet.
- Real failures in `setup-pre-commit.sh` or the commit-msg symlink still mark
  the repo as failed and exit `1`.

**Usage:**

```bash
bash .github/setup-hooks.sh
```

## Adding New Scripts

### `secpal-vulnerability-reevaluation.py`

Pure verification and adaptation boundaries for exact OCI index/platform
identity, authoritative Syft SPDX association, vendor-native Grype/Trivy
evidence, database identity/freshness, trusted reviewed-VEX checkout bytes, and
the versioned re-evaluation run envelope. It rejects noncanonical credentialed
repository paths outside the authenticated caller's exact GHCR namespace and
re-derives trusted policy output plus complete required-operation health from
raw evidence before issue mutation. Its `list-vex` command provides the single
fail-closed regular-file enumeration used by every reviewed-VEX workflow path;
`verify-vex` binds declared repository, ancestor commit, document path, bytes,
and digest to the authenticated checkout. External registry/scanner operations
remain in the reusable workflow.

### `secpal-vulnerability-triage.py`

Validates the run envelope and normalized policy result, then plans or delivers
caller-scoped deterministic GitHub issue updates. It searches every exact-subject
lookup key, retains authenticated historical alias keys on unique updates, fails
closed on ambiguous matches, reconciles healthy inverse transitions, and
maintains stable stale-health alerts without reimplementing vulnerability
policy.

When adding new scripts:

1. Include SPDX headers — either inline in the file or via a `.license` sidecar (both are valid for REUSE compliance)
2. For shell scripts, make executable: `chmod +x scripts/your-script.sh`; Node `.mjs` scripts run via `node` and do not require `+x`
3. Document usage in this README
4. Add CI workflow if appropriate
5. Test across all 4 repositories

## License

All scripts use MIT License unless otherwise specified.
See individual `.license` files for details.
