<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

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

Validates the authoritative `AGENTS.md` baseline, the Copilot compatibility
mirror, and focused instruction overlays across all repositories.

**Usage:**

```bash
# In any repository (.github, api, frontend, contracts)
./scripts/validate-ai-instructions.sh
```

**Tests Performed:**

1. **File Existence**

   - Checks for `AGENTS.md`
   - Checks for `.github/copilot-instructions.md` as compatibility mirror
   - `copilot-config.yaml` check always skips (file removed 2026-04-11)

2. **REUSE Compliance**

   - Validates `AGENTS.md` REUSE metadata
   - Validates `copilot-instructions.md.license` exists when a sidecar is used
   - `copilot-config.yaml.license` check always skips (file removed 2026-04-11)
   - Verifies CC0-1.0 license

3. **Markdown Linting**

   - Runs markdownlint-cli on instructions
   - Uses the repo-pinned `markdownlint-cli` installed by `npm ci`
   - Suggests auto-fix command on failure

4. **Legacy YAML Syntax**

   - Legacy `copilot-config.yaml` syntax check always skips

5. **Runtime Model Check**

   - Verifies `AGENTS.md` is the self-contained authoritative baseline
   - Verifies the Copilot file mirrors `AGENTS.md`

6. **Content Validation**
   - Ensures critical rules/principles section exists
   - Ensures `AGENTS.md` stays below the runtime discovery size limit
   - Ensures AI findings triage guidance exists
   - Ensures provider-neutral review guidelines and no-attribution guidance exist
   - Validates repo-specific risk guardrails and overlay frontmatter

**Exit Codes:**

- `0`: All tests passed
- `1`: One or more tests failed

**Example Output:**

```
=========================================
SecPal AI Instructions Validation
=========================================

Repository Type: api

✓ AGENTS.md exists
✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - removed 2026-04-11)
✓ AGENTS.md has REUSE license
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - removed 2026-04-11)
✓ AGENTS.md passes markdown lint
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - removed 2026-04-11)
✓ repo instructions are self-contained
✓ instructions contain critical rules

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

### `install-polyscope-rollout.sh`

Installs the SecPal Polyscope rollout systemd units that keep workspace clones,
prompts, and preview config in sync. Run this from the workspace root when
`setup-hooks.sh` reports a managed repo as **skipped (missing directory)** so
the rollout-managed workspace can sync back to the expected repository set.

**Usage:**

```bash
bash .github/scripts/install-polyscope-rollout.sh
```

After installation, the user-level `polyscope-rollout-sync.service` and
`polyscope-worktree-provision.service` units take care of provisioning new
managed repositories automatically when the canonical repo list changes.

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
