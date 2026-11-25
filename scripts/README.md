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
  and `vendor/`). Development workspaces use `.context/` to pass
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
Development workspaces need.

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

Canonical GitHub callers supply trusted repository identity via
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
this public required-check inventory. Deployment's existing checks remain
bound to GitHub Actions App `15368`. The review-baseline mode retains its
original six-repository scope and does not manage Deployment's review settings.

**What It Does:**

1. Defines the required status-check contexts per repository in one manifest
2. Builds the exact JSON payload GitHub expects for branch protection updates
3. Applies the payload through `gh api` using `--input` so booleans and arrays stay typed correctly
4. Keeps the live branch-protection baseline repeatable after workflow or context drift
5. Keeps unactivated conditional checks in a separate publication list that is
   never included in an apply payload.
6. Emits `strict: true` while preserving each managed repository's required
   checks and App bindings. Pull request branches must be up to date with
   protected `main` before merging.

**Exit Codes:**

- `0`: Payload printed or sync applied successfully
- `2`: Usage error, unknown repository, or missing dependency

### `setup-hooks.sh`

Installs pre-commit and commit-msg hooks across every managed SecPal repo
discovered next to the `.github` checkout. It also retires legacy
SecPal-managed full-preflight `pre-push` symlinks without touching custom hooks.

**Behavior:**

- Repos that are **missing on disk** are surfaced as a soft warning (separate
  summary line) and the script still exits `0` when every other repo's hooks
  installed cleanly. Use an assigned Herdr checkout or clone the missing
  repository before installing its hooks.
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
can re-derive trusted policy output and complete required-operation health from
raw evidence. Its `list-vex` command provides the single
fail-closed regular-file enumeration used by every reviewed-VEX workflow path;
`verify-vex` binds declared repository, ancestor commit, document path, bytes,
and digest to the authenticated checkout. External registry/scanner operations
remain in the reusable workflow.

When adding new scripts:

1. Include SPDX headers — either inline in the file or via a `.license` sidecar (both are valid for REUSE compliance)
2. For shell scripts, make executable: `chmod +x scripts/your-script.sh`; Node `.mjs` scripts run via `node` and do not require `+x`
3. Document usage in this README
4. Add CI workflow if appropriate
5. Test across all 4 repositories

## License

All scripts use MIT License unless otherwise specified.
See individual `.license` files for details.
