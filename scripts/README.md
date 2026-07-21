<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

## Pull Request Evidence

### `secpal-pr-review.py`

Captures deterministic, thread-aware GitHub pull-request evidence and verifies
immutable evidence and local Git state through a strict read-only command
boundary. `verify-evidence` supports open, closed, and merged snapshots;
`verify-gate` reuses that evidence path and additionally evaluates current
open-PR merge readiness. Neither command authorizes merge. Canonical JSON is
the authority; Markdown is an escaped derived view. The helper performs no
review request, reaction, reply, thread resolution, push, or merge operation.

See [Deterministic PR State and Evidence Layer](../docs/secpal-pr-review-state-layer.md)
for schemas, bounded pagination, signature and required-check semantics, safe
outputs, commands, and Package 2.1 non-goals.

### `secpal-pr-review-actions.py`

Validates deterministic Package-2.2 mutation plans and applies at most one
explicitly selected, anchor-bound reaction, inline evidence reply, or eligible
thread resolution. The helper performs one current-target idempotency read even
in audit mode; a write additionally requires `--apply`. Every plan must match the
checked-in repository registry and binds its finding, target, immutable target
state, counters, and recorded mutation identities before a write. Its exact
command and endpoint allowlists provide no review-request, Ready-transition,
generic API, Git-write, label/issue, merge, or auto-merge capability, and failures
are never retried. It independently verifies Package-2.1 evidence before every
operation; resolutions additionally run all registered local validations and
re-check the complete live thread comment set, applicable required-check rules,
current base, effective check target, and required-check outcomes, then repeat
the PR-wide feedback and exact target reads. Reply targets include their exact
parent node identity. Registry validation permits only the required direct
tools, checked-in scripts, and approved project-script forms before any command
runs. PR-wide feedback must match across two complete bounded projections.
Resolution plans reject
unrecorded already-resolved targets, canonical-reference cycles, unsafe
canonical dispositions, actionable fixes without commit and test proof, and
operations whose evidence does not match their logical finding. Their initial
and final heads must also encode exactly one new linear commit per recorded
signed push, or no commit movement for a no-push session.

### `install-secpal-pr-review-skill.sh`

After Package 2.2 is merged, installs the repository-owned skill as a direct
canonical link under `$HOME/.agents/skills/`. The installer is idempotent,
refuses non-symlink targets and unexpected links, and requires `--repair` before
replacing a wrong link. It compares canonical absolute link text without
GNU-specific `readlink` options and never modifies unrelated user configuration.

See [Finite SecPal PR review workflow](../docs/secpal-pr-review-workflow.md) for
explicit invocation, state limits, classification, guarded action ordering,
registry decisions, recovery, and post-merge rollout prerequisites.

## Validation Scripts

### `check-domains.sh`

Enforces the SecPal `secpal.*` namespace split. The script greps text files
in the working tree (via `grep -r --include=...`, so untracked files matching
the include patterns are inspected too) for any `secpal.<something>`
substring and flags entries that fall outside the approved set
(`secpal.app`, `changelog.secpal.app`, `apk.secpal.app`, `secpal.dev`,
`api.secpal.dev`, `app.secpal.dev`, plus arbitrary `*.preview.secpal.dev`
previews). It also surfaces `api.secpal.app`, the deprecated `.app` web
host, so callers cannot reintroduce it as an active host.

**Scope (intentional limit):**

- The match regex is `secpal\.[A-Za-z0-9.-]+`, so only `secpal.*` strings are
  ever inspected. Non-`secpal` domains are out of scope by design — even when
  they belong to SecPal (e.g. `guardguide.de`).
- SecPal-owned external hosts such as `guardguide.de` (managed via
  SecPal/.github#483) are governed by their own repository policy guards and
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

Audits Epic issues and reports checklist drift, such as closed child issues
that remain unchecked in open or closed epics, or child issues that are still
open even though the parent epic is already closed.

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

1. Node.js 22 and `npm`
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
   - Accepts allowed inline SPDX metadata or a valid `.license` sidecar

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

**Repository Detection:**

The script automatically detects repository type:

- **org**: `.github` repository (org-wide instructions)
- **api**: Laravel API (has `artisan`, `composer.json`)
- **frontend**: React frontend or Android wrapper (has `package.json` with `vite`)
- **changelog**: Next.js changelog site (has `next.config.mjs`)
- **website**: Astro landing page (has `astro.config.mjs`)
- **contracts**: OpenAPI contracts (has `package.json` with `openapi` or `docs/openapi.yaml`)

### `sync-required-checks.sh`

Builds and applies the repository-specific required status-check payloads for
the SecPal application repositories.

**Usage:**

```bash
# Inspect the payload for one repository without writing to GitHub
bash scripts/sync-required-checks.sh --repo guardguide.de --print-payload | jq

# Apply the configured payload to one repository
bash scripts/sync-required-checks.sh --repo api --apply

# Apply the configured payloads to every managed repository
bash scripts/sync-required-checks.sh --apply
```

**Managed Repositories:**

- `.github`
- `api`
- `changelog`
- `frontend`
- `contracts`
- `android`
- `secpal.app`
- `GuardGuide`
- `guardguide.de`

**What It Does:**

1. Defines the required status-check contexts per repository in one manifest
2. Builds the exact JSON payload GitHub expects for branch protection updates
3. Applies the payload through `gh api` using `--input` so booleans and arrays stay typed correctly
4. Keeps the live branch-protection baseline repeatable after workflow or context drift

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
authorization is unavailable.

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
reconciliation removes only those recorded broken aliases. The paired daily
`polyscope-clone-reaper.timer` removes only aged orphan clone roots after
checking the live database allowlist, locks, and processes.

Every generated repository setup sequence starts with the validation-only
`--validate-instruction-worktree` command inside one strict shell entry. That
entry groups the complete native setup with fail-fast semantics, so validation
or any later command failure prevents every remaining npm, Composer, `.env`,
database, migration, seed, build, or repository setup command. The external
provisioner applies the same canonical contract before its local configuration,
hook, alias, setup, and marker writes.

The worktree provision service waits three seconds before each activation to
coalesce SQLite event bursts and takes a process-shared lock before provisioning.
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

After both installation steps, verify the steady state:

```bash
sudo -k -n /usr/local/libexec/secpal-polyscope-nginx-apply --check
systemctl --user is-active polyscope-rollout-sync.path
systemctl --user is-active polyscope-worktree-provision.path
systemctl --user is-active polyscope-worktree-provision.timer
systemctl --user is-active polyscope-clone-reaper.timer
```

### `setup-hooks.sh`

Installs pre-push, pre-commit, and commit-msg hooks across every managed
SecPal repo discovered next to the `.github` checkout.

**Behavior:**

- Repos that are **missing on disk** are surfaced as a soft warning (separate
  summary line) and the script still exits `0` when every other repo's hooks
  installed cleanly. Run `.github/scripts/install-polyscope-rollout.sh` (or
  sync via Polyscope) to recover the rollout-managed workspace state.
- Managed repo paths that exist but are **not directories** are treated as real
  failures because they indicate a corrupted workspace layout, not a repo that
  simply has not been synced yet.
- Real failures in `setup-pre-push.sh`, `setup-pre-commit.sh`, or the
  commit-msg symlink still mark the repo as failed and exit `1`.

**Usage:**

```bash
bash .github/setup-hooks.sh
```

## Adding New Scripts

When adding new scripts:

1. Include SPDX headers — either inline in the file or via a `.license` sidecar (both are valid for REUSE compliance)
2. For shell scripts, make executable: `chmod +x scripts/your-script.sh`; Node `.mjs` scripts run via `node` and do not require `+x`
3. Document usage in this README
4. Add CI workflow if appropriate
5. Test across all 4 repositories

## License

All scripts use MIT License unless otherwise specified.
See individual `.license` files for details.
