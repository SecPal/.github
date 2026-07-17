<!-- SPDX-FileCopyrightText: 2026 SecPal Contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Changelog

Log of notable changes to SecPal organization defaults (newest first).

**Note:** This repository contains organization-wide configuration and is NOT versioned. For versioned releases, see individual project repositories (`api/`, `frontend/`, `contracts/`).

---

## 2026-07-17 - Coordinate Polyscope Plan And Autopilot Modes

**Fixed:**

- provisioned a scoped global Codex instruction that keeps Plan strictly analysis-only, records required GitHub and branch setup as the first dependency-ordered Autopilot stories, and requires execution to continue in the resulting writable context
- prevented sandbox, approval, or network denials from being misreported as user cancellations or invalid GitHub credentials without corresponding evidence
- partitioned cross-repository plans by linked workspace root and explicitly delegated each repository scope to its own subagent during Autopilot execution
- added rollout regression coverage for installing the global instruction without overwriting unrelated user guidance and for keeping its source under the existing rollout watcher

---

## 2026-07-15 - Fix Instruction Validation During Push

**Fixed:**

- scoped the extra-blank-line exception to the authoritative and mirrored instruction files, so formatting-only whitespace differences no longer block validated pushes without weakening repository-wide Markdown validation
- added positive and negative regression coverage for the file-local exception and continued enforcement in ordinary Markdown files, requiring the directive in each instruction header and the lockfile-installed Markdownlint binary for self-contained validation

---

## 2026-07-15 - Replace Deprecated Project Token Input

**Fixed:**

- replaced the deprecated `app-id` input with `client-id` in every GitHub App token step of `.github/workflows/project-automation-core.yml` while retaining the existing `APP_ID` and `APP_PRIVATE_KEY` caller secret contract
- added a focused project-automation workflow regression test to prevent reintroducing the deprecated input and verify all token steps retain that secret wiring

---

## 2026-07-15 - Pin Nested Dependabot Workflow Actions

**Fixed:**

- pinned `lewagon/wait-on-check-action` and both `actions/github-script` invocations in `.github/workflows/reusable-dependabot-auto-merge.yml` to immutable commits, so callers pinned to a reviewed reusable-workflow commit cannot execute code changed through movable nested action tags
- extended `tests/dependabot-auto-merge.sh` with semantic YAML fixtures that cover named and shorthand steps, quoted and flow-style references, lowercase and uppercase repository commit pins, canonical lowercase Docker digests, and rejection of caller-local actions; the parser uses the installed dependency when available and the repository's existing pinned-`npx` preflight model in clean checkouts while retaining Dependabot's daily `github-actions` update configuration

---

## 2026-07-12 - Reap Orphaned Polyscope Worktree Directories

**Fixed:**

- extended the scheduled Polyscope reaper to reclaim aged, unregistered immediate worktree directories below protected clone roots while preserving active `worktrees.path` records, clone-root worktrees, hidden metadata, locks, live processes, and paths outside the clone root
- pinned final worktree detachment to non-symlink parent-directory handles, revalidated candidates after process scans before dry-run measurement, and moved recoverable quarantines to the clone root, preventing parent-swap path escapes and stranded cleanup after interruptions
- added positive and negative fixtures for nested worktree deletion, dry runs, active registrations, grace periods, locks, active processes, symlink escapes, parent swaps, and interrupted quarantine deletion

---

## 2026-07-12 - Import Address Data into API Previews

**Fixed:**

- imported the address dataset during API Polyscope workspace bootstrap when absent, matching the API setup workflow so newly provisioned previews retain address lookup functionality
- stopped the automatic worktree-provisioning service from synchronizing the Polyscope database it watches, preventing its own metadata write from repeatedly retriggering the path unit while retaining immediate event-driven provisioning
- serialized staged frontend preview builds and stopped the provision watcher from observing clone contents it changes itself, so every published HTML document, JavaScript bundle, and service worker comes from one completed build
- passed the canonical Polyscope workspace name to generated frontend browser smokes, so hash-suffixed clone directories continue to test the public canonical preview host instead of a non-existent physical-name host

---

## 2026-07-12 - Reap Orphaned Polyscope Clone Roots

**Fixed:**

- added a daily, conservative Polyscope clone-root reaper that derives its allowlist from live `polyscope.db` worktree paths, waits a seven-day grace period, rejects paths outside the configured clone root, skips active processes and lock files, supports dry-run and JSON reporting, and reports reclaimed storage
- added positive and negative fixtures covering registered roots, fresh roots, locks, active processes, dry runs, invalid clone roots, and actual deletion; rollout installation now enables the reaper timer
- protected all registered repository roots and added transactional final revalidation plus atomic quarantine before deletion to prevent concurrent registration from racing cleanup

---

## 2026-07-12 - Recover Frontend Preview Watcher After Dependency Installation

**Fixed:**

- made the frontend Polyscope build watcher observe npm's hidden installed-dependency lockfile, so one rebuild follows a setup-time `npm ci` race that initially leaves `cross-env` unavailable; ordinary failures and permanently missing dependencies still wait for a later change instead of retrying continuously

---

## 2026-07-12 - Recover Stale Polyscope Preview Tenant Keys

**Fixed:**

- recovered isolated API previews whose seeded tenant envelope keys no longer match their per-worktree KEK: provisioning now requires the precise `TenantKey::loadKek()` / `unwrapDek()` stack and `Failed to unwrap DEK` error, removes only the preview-local KEK, resets only that preview database or schema, and retries seeding once; unrelated seed failures still surface normally

---

## 2026-07-10 - Canonicalize Polyscope Preview Hosts

**Fixed:**

- canonicalized physical hash-suffixed Polyscope preview hosts by resolving provision markers from the clone root rather than relying on the Expose process working directory, and emit only the canonical host in both successful announcement fields so clone storage names such as `misty-vulture-26c1f2f1` cannot leak into the displayed preview URL; if canonical provisioning metadata is unavailable, the wrapper fails closed instead of publishing the suffixed host
- made the rollout sync install and reload its rendered nginx configuration, preventing removed routing guards from remaining active on the preview host after the provisioning source has been updated
- made automatic nginx installation transactional and safe for unattended rollout: installations fail before service setup when non-interactive privileges are unavailable, privileged commands cannot prompt inside the user service, root execution does not require a sudo binary, unchanged configurations skip backup and reload, and validation or reload failures restore and revalidate the previous configuration
- made the autostarted frontend build watcher retry after setup-time dependency installation by tracking npm metadata, `cross-env`, and Vite rather than waiting for an unrelated source edit

## 2026-07-10 - Gate API Preview Readiness

**Fixed:**

- delayed the API preview tunnel's ready announcement until its public `/health/ready` endpoint returns a 2xx response, so Polyscope does not present an API preview as ready while nginx or Laravel provisioning still returns a generic `404` or a redirect; the ten-minute default wait window covers provisioning after the three-minute fallback timer, while static previews retain their immediate announcement behavior

---

## 2026-07-10 - Restrict Reusable Workflow Token Permissions

**Fixed:**

- added explicit least-privilege permission ceilings to the reusable actionlint, Node.js, PHP, PR-size, and REUSE workflows; actionlint can write checks, PR-size can read pull-request metadata, and the remaining audited workflows only read repository contents
- extended the reusable-workflow policy regression test and preflight guidance so every `.yml` or `.yaml` reusable workflow must retain a valid, non-null top-level `permissions` block as well as job timeouts
- added focused positive and negative fixtures for mapping and deny-all permissions, missing or null permissions, and missing timeouts so the policy scanner cannot silently lose coverage

---

## 2026-07-10 - Start API Preview Queue Workers Automatically

**Fixed:**

- marked the generated API preview Queue Worker action as autostarted and kept it running without a supervisor-dependent time limit, so scheduled forensic jobs continue to be consumed and readiness does not become blocked by a missing worker heartbeat

---

## 2026-07-09 - Clean Up Repository-Wide yamllint Warnings

**Fixed:**

- added YAML document start markers across the warned GitHub workflow files, refreshed touched SPDX year headers, and wrapped overlong workflow command and script lines so `yamllint .github/workflows/` now completes without repository-wide warning noise
- replaced the folded `python -c` REUSE.toml checks in the local and reusable license-compatibility workflows with heredoc-fed Python, preventing indentation-driven runtime failures when repositories use custom LicenseRefs in `REUSE.toml`, and extended `tests/license-compatibility.sh` so future workflow refactors must preserve that execution shape
- refreshed the touched workflow sidecar SPDX years in `.github/workflows/validate-copilot-instructions.yml.license` and `.github/workflows/pr-size.yml.license` so edited sidecar-licensed workflows stay REUSE-accurate
- kept the repository lint policy explicit by adding a document start marker to `.yamllint.yml` itself instead of leaving YAML style drift as ad hoc warning output

---

## 2026-07-09 - Remove Dependabot Auto-Merge Self-Tag Drift

**Fixed:**

- switched `.github/workflows/dependabot-auto-merge.yml` from the stale `SecPal/.github@v1` tag to the reviewed `SecPal/.github/.github/workflows/reusable-dependabot-auto-merge.yml@main` ref, so this repository no longer depends on an outdated published tag while keeping auto-merge decisions on reviewed workflow code
- updated `.github/workflows/reusable-dependabot-auto-merge.yml`, `.github/instructions/github-workflows.instructions.md`, and `.github/copilot-instructions.md` to tell cross-repository callers to pin reusable workflows to a reviewed immutable commit SHA instead of `@main` or the stale `@v1` example
- updated `EXAMPLE_workflow_for_other_repos.yml` and extended `tests/dependabot-auto-merge.sh` so cross-repository reference patterns now use immutable commit SHA placeholders and the caller workflow cannot regress to a local reusable workflow path, stale `@v1` tag, or moving example refs
- updated `.github/workflows/README.md` to align every cross-repository reusable workflow example with the immutable SHA-pinning guidance instead of moving `@main` refs, and refreshed the touched example file SPDX years
- updated `docs/workflows/ROLLOUT_GUIDE.md` and the cross-repository guidance comments in `.github/workflows/quality.yml` so the remaining reusable workflow copy-paste examples no longer point consumers at moving `@main` refs
- updated the rollout guide's later maintenance section so it now describes rotating reviewed commit SHAs instead of auto-tracking `@main` or pinning release tags, and refreshed the touched `quality.yml` SPDX year
- narrowed the rollout-guide `@main` regression guard in `tests/dependabot-auto-merge.sh` to anchored YAML `uses:` lines, including quoted and inline-comment variants, so prose can warn against moving refs without falsely tripping the pinning check

---

## 2026-07-08 - Harden Polyscope Workspace Provisioning Triggers

**Fixed:**

- persisted source PostgreSQL `DB_PASSWORD` values back into generated API preview worktree `.env` files during `ensure_api_worktree_ready()` and refreshed them after source password rotation, so PHP-FPM runtime requests no longer fail with `fe_sendauth: no password supplied` after otherwise successful preview provisioning
- tracked source-managed preview passwords with a hash snapshot so manual worktree `DB_PASSWORD` overrides are preserved, source-password removals clear stale preview secrets, and `refresh_api_worktree()` repairs existing `.env` files before rerunning artisan refresh steps
- kept schema-mode preview `DB_URL` values password-free while still persisting `DB_PASSWORD` separately in the worktree `.env`, avoiding credential leaks in connection URLs
- updated `scripts/install-polyscope-rollout.sh` so the installed `polyscope-worktree-provision.path` watches `~/.polyscope/polyscope.db-wal` with `PathModified=`, ensuring fresh workspace creation triggers automatic SecPal worktree provisioning on WAL appends instead of waiting for the SQLite writer to close `polyscope.db`
- also watched `$POLYSCOPE_CLONE_ROOT` with `PathModified=` and installed a three-minute `polyscope-worktree-provision.timer` fallback so nested workspace-directory creation under existing repository clone roots is still provisioned when the non-recursive path unit cannot observe it directly
- stopped explicitly starting `polyscope-worktree-provision.service` during installation so the newly enabled timer and path units do not immediately stack duplicate provisioning runs on already-booted machines
- moved the provision path/timer activation until after the initial rollout sync and raised the provisioning burst budget to five starts per five minutes, preventing the three-minute fallback timer from consuming nearly all rate-limit headroom for real workspace events
- switched the fallback timer's first trigger from `OnBootSec=30s` to `OnStartupSec=30s`, so user-manager restarts do not treat the initial delay as already elapsed and race provisioning against the first rollout sync
- extended `tests/polyscope-rollout.sh` to fail if the installed `polyscope-worktree-provision.path` ever drops either the `polyscope.db-wal` or clone-root provisioning watches, or if the timer fallback is not installed and enabled

---

## 2026-07-07 - Fix Direct Deploy Repo Name Validation

**Fixed:**

- removed shell-style quoting from `.github/workflows/reusable-deploy-main.yml` when calling the VPS `deploy <repo>` wrapper, because the forced command receives those quotes literally and rejects names such as `'.github'` as invalid
- validated `github.event.repository.name` locally against the deploy host's allowed `^[A-Za-z0-9._-]+$` contract before invoking the direct `deploy <repo>` command
- updated `tests/deploy-main-workflow.sh` so regression coverage now checks direct validated repo-name handoff instead of shell-quoted wrapper arguments

---

## 2026-07-07 - Fix VPS Deploy Wrapper Command

**Fixed:**

- changed `.github/workflows/reusable-deploy-main.yml` to call the VPS wrapper on its allowed direct `deploy <repo>` path instead of wrapping the remote command in `sh -c`, which the production deploy host rejects with `Command not allowed`
- updated `tests/deploy-main-workflow.sh` so regression coverage now checks the direct deploy-wrapper command shape and preserves quoted repository-name handoff without relying on a shell-wrapper simulation that the VPS does not allow

---

## 2026-07-07 - Add Main-Branch VPS Deploy Workflow

**Added:**

- added `.github/workflows/deploy-main.yml` as the repo-local caller and `.github/workflows/reusable-deploy-main.yml` as the reusable VPS deploy workflow, so deployable repositories can invoke the same guarded `deploy <repo>` flow through `workflow_call`
- kept the reusable deploy command on the VPS wrapper's direct `deploy <repo>` path with exact least-privilege permissions, explicit empty reusable token permissions, SSH host verification, queued per-repository concurrency, declared workflow-call secrets, and shell-quoted repository-name handoff
- mapped only the five required `VPS_*` secrets from the caller workflow into the reusable deploy workflow instead of inheriting every caller secret
- added `tests/deploy-main-workflow.sh` and wired it into `scripts/preflight.sh` so future edits keep the caller and reusable workflow contract for headers, permissions, timeout coverage, explicit secret mapping, reusable invocation, direct deploy-wrapper compatibility, queued deployment concurrency, and safe repository-name handoff under regression coverage

---

## 2026-07-07 - Stabilize Polyscope API Runtime Credentials

**Fixed:**

- routed generated API preview run actions for `queue:work`, `schedule:work`, and `pail` through `scripts/polyscope-rollout.py`, so long-running preview processes now inherit the same transient PostgreSQL password injection already used during bootstrap and refresh
- made the API runtime wrapper hand off to the long-running artisan process with `exec`, avoiding stale child processes when Polyscope replaces or stops preview run actions
- extended `tests/polyscope-rollout.sh` to fail if API runtime commands ever regress to direct artisan invocations without the rollout wrapper, depend on display labels for wrapping, keep a parent wrapper process alive, or stop propagating transient `DB_PASSWORD` and `PGPASSWORD` values into those long-running preview processes

---

## 2026-07-06 - Restrict GitHub Actions Dependabot Fallback

**Fixed:**

- limited the metadata-empty PR-title fallback in `.github/workflows/reusable-dependabot-auto-merge.yml` to non-`github-actions` ecosystems so GitHub Actions bumps with incomplete `fetch-metadata` version outputs stay on manual review instead of being auto-merged from semver-shaped titles
- extended `tests/dependabot-auto-merge.sh` to fail if the reusable workflow ever re-enables PR-title fallback for metadata-empty `github-actions` Dependabot updates

---

## 2026-07-06 - Fix Dependabot Auto-Merge Classification

**Fixed:**

- replaced PR-title parsing in `.github/workflows/reusable-dependabot-auto-merge.yml` with official `dependabot/fetch-metadata` outputs so Dependabot auto-merge decisions now follow GitHub-provided update metadata instead of brittle `Bump ... from ... to ...` title strings
- classified GitHub Actions workflow-reference bumps pinned to commit SHAs as explicit manual-review updates, avoiding false `unparseable` failures when Dependabot opens PRs such as `chore(deps): Bump ... from <sha> to <sha>`
- aligned the reusable workflow's Phase 3 behavior with Dependabot policy by keeping major version updates on manual review in every phase
- updated `dependabot/fetch-metadata` to the upstream `v3.1.0` commit so the reusable workflow picks up the null `update-type` fix for Python, Composer, and Terraform Dependabot PRs instead of misrouting those updates to manual review
- restored a bounded PR-title semver fallback for non-`github-actions` ecosystems when `fetch-metadata` still returns empty outputs, preserving patch/minor auto-merge behavior for repositories hit by upstream null-`update-type` gaps
- kept `dependabot/fetch-metadata` verification enabled while soft-failing metadata retrieval into explicit manual review, so maintainer-touched or otherwise unverifiable Dependabot PRs no longer bypass commit validation or strand the workflow in a hard failure state
- fail-closed grouped Dependabot PRs to manual review because the upstream `update-type` output only reports the highest semver change for the group, which is not sufficient proof that every dependency in the PR is semver-safe to auto-merge
- removed invalid caller-workflow `timeout-minutes` syntax from the reusable Dependabot workflow invocation while retaining timeouts inside the called workflow jobs
- fixed the caller workflow to contain only one YAML document start marker and updated the reusable workflow's header example to show callers pinning to `@v1`
- extended `tests/dependabot-auto-merge.sh` to fail if the reusable workflow regresses on the bounded metadata-empty title fallback, drifts off the pinned `fetch-metadata` fix, stops fail-closing grouped or maintainer-changed Dependabot PRs, reintroduces duplicate or malformed caller document markers, or drifts back to `@main` in the usage example

---

## 2026-07-06 - Harden Polyscope Preview Rollout

**Fixed:**

- kept displayed preview URLs and linked-workspace preview hosts pinned to the original provisioned workspace slug after later workspace-path renames, while normalizing marker-derived workspace values before they are used in aliases or hostnames
- kept source PostgreSQL passwords transient during preview database provisioning and bootstrap commands instead of persisting them into generated API worktree `.env` files
- kept generated inline linked-workspace resolvers from creating empty SQLite files when the configured Polyscope database path is missing
- passed PostgreSQL host, port, and username explicitly to `psql` during preview database management and covered the command shape in rollout regression tests
- made generated API `polyscope.local.json` configs start a dedicated `php artisan schedule:work` background run action automatically, so preview API workspaces keep Laravel scheduler tasks running without manual startup

---

## 2026-07-06 - Fix Dependabot Auto-Merge Caller Workflow Parsing

**Fixed:**

- removed the invalid `timeout-minutes` key from the `jobs.auto-merge` reusable-workflow caller in `.github/workflows/dependabot-auto-merge.yml`, so GitHub no longer rejects the workflow at parse time before any Dependabot auto-merge job can start
- added a regression check in `tests/dependabot-auto-merge.sh` to keep reusable-workflow caller jobs from reintroducing job-level keys that GitHub disallows alongside `uses:`
- documented the reusable-workflow caller timeout exception in both the root and focused workflow instructions while keeping timeout coverage required inside called reusable workflows

---

## 2026-07-06 - Clean Up Dependabot Workflow yamllint Warnings

**Fixed:**

- added YAML document start markers and wrapped overlong strings in the reusable and caller Dependabot auto-merge workflows so `yamllint` no longer reports style-noise warnings for those files

---

## 2026-07-05 - Fix Polyscope Preview Workspace Bootstrap

**Fixed:**

- preserved collision-aware hashed workspace slugs when linked-worktree lookups resolve through normalized Polyscope alias paths, keeping frontend and API preview hostnames aligned even after the database stores the alias path instead of the physical directory
- updated `scripts/polyscope-rollout.py` so Polyscope path normalization now updates the matched `worktrees` row by id after resolved-path lookup, allowing preview alias rewrites to persist even when the stored database path string differs from the filesystem-resolved path
- stripped legacy hash-suffixed fallback workspace directory names from Polyscope preview URL generation when git branch or database metadata is unavailable, while keeping the full hashed slug whenever stripping would collide with another sibling worktree
- normalized path-derived Polyscope workspace names into DNS-safe preview host labels before writing URLs, aliases, or local preview config, without using GitHub branch, PR, or issue metadata for hostnames
- added rollout regression coverage for both the resolved-path database update case and the fallback preview-hostname normalization path
- changed Polyscope API worktree preparation to create missing worktree `.env` files from `api/.env.example` instead of copying the source checkout `.env`, so each workspace starts from the committed template rather than inheriting the source workspace verbatim
- preserved only template-defined local base values needed for workspace bootstrap when generating a missing worktree `.env`, still leaving source-only secrets out of new worktrees, avoiding reuse of the source `APP_KEY`, and keeping generated worktree `.env` files free of source `DB_PASSWORD` values even for PostgreSQL-backed previews
- rewrote API preview `KEK_PATH` values to a writable per-worktree storage path so first-run seeders can create tenant key material inside each preview workspace instead of failing against the container-only `/home/appuser/.secrets` path from `api/.env.example`, and quote generated path values when the physical worktree path contains spaces
- switched generated Polyscope preview URL templates from the raw `{{folder}}` placeholder to `{{worktree}}` so displayed preview hosts follow the resolved workspace name instead of leaking the underlying directory name into newly created workspace URLs
- kept the preview rewrite step on top of the generated template so each workspace now receives its own preview-facing `APP_URL`, linked `FRONTEND_URL`, and per-workspace PostgreSQL settings without manual correction after creation
- routed generated API setup through the rollout bootstrap command so new preview worktrees can borrow source PostgreSQL credentials transiently for database provisioning, migrations, and seeding without persisting those credentials into the generated worktree
- routed the destructive `Preview Only: Refresh DB + E2E User` Polyscope action through the same rollout bootstrap path so PostgreSQL-backed preview refreshes keep borrowing source-only DB credentials transiently instead of failing once the worktree `.env` leaves `DB_PASSWORD` blank
- aligned Polyscope rollout regression coverage and preview URL template assertions with the current `{{worktree}}` placeholder used for path-derived preview hostnames
- removed an impossible rollout assertion for a nonexistent `--api-worktree-migration-command` flag so the API preview config regression test matches the generated refresh command it actually validates

---

## 2026-07-04 - Document SecPal Licensing, CLA, And Attribution Policy

**Changed:**

- added a central [`docs/licensing-policy.md`](docs/licensing-policy.md) reference for SecPal-wide CLA definitions, `SecPal Contributors` SPDX policy, `LicenseRef-SecPal-Attribution` usage, third-party notice separation, Tailwind-specific scoping, and the enforceable versus preferred SecPal attribution wording
- added the approved [`LICENSES/LicenseRef-SecPal-Attribution.txt`](LICENSES/LicenseRef-SecPal-Attribution.txt) addendum text to this repository so shared governance docs can reference the exact attribution terms already enforced by the reusable license-compatibility workflows
- updated [`CLA.md`](CLA.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`README.md`](README.md), and [`docs/brand/licensing-wording.md`](docs/brand/licensing-wording.md) so contributor-facing guidance now defines `SecPal`, `Project Maintainer`, and CLA recipient scope consistently and points repository owners at the central licensing policy
- fixed the local and reusable license-compatibility workflows so their custom-license guard searches real `SPDX-License-Identifier` headers when validating `LicenseRef-SecPal-Attribution` metadata
- aligned the custom-license regression fixtures in `tests/license-compatibility.sh` with the new `SecPal Contributors` copyright policy so review guidance and fixture data do not drift
- cross-referenced the repository-specific rollout issues for `api`, `frontend`, and `android` so the implementation work stays tracked outside the central policy issue

---

## 2026-07-04 - Allow SecPal Attribution LicenseRef In Compatibility Checks

**Fixed:**

- added `LicenseRef-SecPal-Attribution` to the shared AGPL compatibility allowlist so SecPal repositories using the central attribution policy no longer fail reusable license-compatibility checks
- constrained `LicenseRef-SecPal-Attribution` in the shared license-compatibility workflows so callers must ship the approved SecPal attribution addendum text and may only pair that license reference with files that also declare `AGPL-3.0-or-later`
- hardened both license-compatibility workflows to validate tracked SPDX expressions for `LicenseRef-SecPal-Attribution` and `LicenseRef-TailwindPlus`, rejecting `OR`-paired custom-license expressions and mismatched license-file text
- restored per-file REUSE metadata enforcement for custom license references and stripped `git grep` path prefixes before checking SPDX expressions, closing false passes where `AGPL-3.0-or-later` appeared only in a file path or only on a different file's SPDX metadata
- aligned the repository-local `license-compatibility.yml` allowlist with the reusable workflow so SecPal-specific approvals such as `ODbL-1.0`, `LicenseRef-TailwindPlus`, and `LicenseRef-SecPal-Attribution` cannot drift between the two definitions
- extended the license-compatibility regression test to cover the SecPal attribution LicenseRef, compare local and reusable allowlist license identifiers, and keep the preflight failure guidance aligned with both workflow allowlists
- extended the same regression to verify the SecPal attribution guard block in both license-compatibility workflows so local and reusable enforcement cannot silently drift

---

## 2026-07-04 - Disable SSI For Frontend Preview HTML

**Fixed:**

- disabled nginx SSI processing for Polyscope frontend preview `index.html` and SPA fallback responses, preventing workspace-controlled HTML from reflecting request headers such as cookies and reverting frontend preview HTML to the safe relaxed static CSP once nonce expansion was removed
- widened the relaxed static preview CSP so inline `<style>` elements remain allowed after SSI and nonce expansion were removed from frontend preview HTML delivery
- removed the obsolete preview-only `$preview_uses_ssi` nginx toggle after SSI enablement paths were deleted, so the rendered config no longer carries dead state that could mislead future changes
- updated the Polyscope rollout regression test to reject SSI handoff locations and any `ssi on;` directive in rendered preview nginx configuration

---

## 2026-07-04 - Pin Copilot Review Memory Checkout

**Fixed:**

- pinned the Copilot Review Memory workflow checkout to the current trusted pull request base ref for `pull_request_review` events before running local scripts with the GitHub App token
- added regression coverage so the workflow cannot silently return to the default review-event checkout when executing repository scripts with privileged credentials
- tightened the Copilot review memory regression so it now anchors the trusted review-event checkout `ref` to the active `actions/checkout` step instead of accepting commented or unsafe `ref` lines
- hardened the Copilot review memory regression diagnostics so missing checkout or script lines now fail with the dedicated privilege-boundary message instead of exiting early under `set -euo pipefail`
- kept local preflight usable in checkouts without `origin/HEAD` so the required workflow validation can fall back to `main` instead of exiting early

## 2026-07-04 - Harden Polyscope API Preview Env Handling

**Fixed:**

- stopped Polyscope API worktree preparation from copying the source API `.env` into worktrees that do not already have their own preview `.env`, keeping source secrets and database credentials out of untrusted or external-branch preview setup commands
- disabled gitignored-file copying in generated API `polyscope.local.json` configs so Polyscope no longer pre-populates new API worktrees with the source checkout `.env` before the fail-closed preview setup guard runs
- added regression coverage to ensure missing API worktree `.env` files fail closed without inheriting source checkout secrets

---

## 2026-07-03 - Provision Android SDK Metadata For Polyscope Workspaces

**Fixed:**

- updated `scripts/polyscope-rollout.py` so SecPal Android workspaces and provisioned Polyscope clones now receive `android/local.properties` automatically, using `POLYSCOPE_ANDROID_SDK_ROOT`, `ANDROID_SDK_ROOT`, `ANDROID_HOME`, or `$HOME/Android/Sdk` to keep direct `./gradlew` runs from failing when the shell did not preload Android environment variables
- extended `scripts/check-system-requirements.sh` with an Android-specific repository mode that validates Node 22, Java 21, `javac`, `sdkmanager`, `adb`, the resolved SDK directory, Android local Node dependencies, and the committed native `android/` project layout
- aligned the Android requirements check with the rollout SDK resolution order, made Node 22 failures block `--repo=android`, removed the stray local-dependencies heading when no sibling `android/` repo is present, and hardened the regression test to use a sandboxed SDK path instead of host state
- tightened the Android Java toolchain validation so a `JAVA_HOME` runtime without its matching Java 21 `javac` no longer passes by falling back to a different compiler found on `PATH`
- documented the Android toolchain baseline and the new `--repo=android` verification path in `WORKSPACE_SETUP.md`, `docs/scripts/CHECK_SYSTEM_REQUIREMENTS.md`, and `scripts/README.md`
- added regression coverage for both the rollout-generated Android `local.properties` contract and the Android system-requirements checks

---

## 2026-06-27 - Make AGENTS The Authoritative AI Runtime Baseline

**Fixed:**

- flipped the SecPal AI-governance model so each managed repository now treats its root `AGENTS.md` as the authoritative, provider-neutral runtime baseline for AI-assisted development and review tooling
- updated `scripts/polyscope-rollout.py` so generated Polyscope task prompts and rollout summaries now point at repo-local `AGENTS.md`, while `.github/copilot-instructions.md` is regenerated as a compatibility mirror for tooling that auto-loads the Copilot path
- normalized blank-line runs when `scripts/validate-ai-instructions.sh` compares `.github/copilot-instructions.md` against authoritative `AGENTS.md`, so regenerated mirrors no longer fail on formatting-only newline collapse
- introduced `scripts/validate-ai-instructions.sh` as the canonical validator, kept `scripts/validate-copilot-instructions.sh` as a compatibility wrapper, and extended regression coverage so repositories now fail governance validation when `AGENTS.md` is missing or weak, or when `.github/copilot-instructions.md` stops clearly mirroring the authoritative `AGENTS.md`
- added provider-neutral `Review guidelines` and no-attribution/no-self-promotion rules to each managed `AGENTS.md`, so AI review output focuses on evidence, impact, and fix paths instead of tool identity
- extended `scripts/validate-ai-instructions.sh` and regression coverage to enforce provider-neutral review guidance and keep `AGENTS.md` below the default runtime discovery size limit
- narrowed GuardGuide package-name detection in `scripts/validate-ai-instructions.sh` to exact `guardguide` manifests, so Astro sites such as `guardguide.de` keep the `website` validator path instead of being misclassified as the GuardGuide app
- aligned the AGENTS rollout with the merged `markdownlint-cli@0.49.0` toolchain from PR 506 instead of reintroducing `markdownlint-cli2`
- documented the new split between authoritative `AGENTS.md`, Copilot compatibility mirrors, and focused `.github/instructions/*.instructions.md` overlays in `docs/development-principles.md` and `docs/VALIDATION_SYSTEM.md`

---

## 2026-06-27 - Replace markdownlint-cli2 With markdownlint-cli

**Changed:**

- replaced `markdownlint-cli2` with `markdownlint-cli@0.49.0` in the local
  Node toolchain so the repository keeps the same markdownlint rule set while
  dropping the dependency path that triggered the remaining moderate
  `npm audit` findings
- updated `scripts/preflight.sh`, `scripts/validate-copilot-instructions.sh`,
  `.github/workflows/quality.yml`, and `reusable-markdown-lint.yml` to invoke
  `markdownlint-cli` with explicit `--ignore` exclusions and `.markdownlint`
  config handling
- updated markdown lint documentation, system requirements guidance, and the
  focused preflight regression test to match the new CLI path

**Fixed:**

- `npm audit` now returns zero vulnerabilities for the local `.github`
  markdown lint toolchain after removing `markdownlint-cli2`

---

## 2026-06-27 - Fix Review Findings from markdownlint-cli2 Audit Migration

**Fixed:**

- added missing `permissions: contents: read` to `reusable-markdown-lint.yml`
  so the reusable job no longer inherits elevated permissions from calling
  workflows (least-privilege compliance)
- restored `--yes` fallback in `scripts/preflight.sh`: the script now prefers
  the local `node_modules/.bin/markdownlint-cli2` when available, and falls
  back to `npx --yes` with an explanatory message when `npm ci` has not been
  run, preventing a hang or silent failure in pre-push hooks
- documented the `governance-ref` supply-chain risk in both
  `reusable-markdown-lint.yml` and `reusable-copilot-instructions.yml` input
  descriptions: callers can pin to a commit SHA to prevent the `main`-tracking
  default from pulling an updated binary unexpectedly

---

## 2026-06-27 - Track Remaining markdownlint-cli2 Audit Findings

**Added:**

- pinned `markdownlint-cli2@0.22.1` in `package.json` and `package-lock.json`
  so local markdown linting now runs from repo-owned dependencies after
  `npm ci`

**Changed:**

- updated `scripts/preflight.sh`, `scripts/validate-copilot-instructions.sh`,
  `.github/workflows/quality.yml`, and the reusable markdown/Copilot workflows
  to use the pinned local `markdownlint-cli2` instead of global installs or
  interactive `npx --yes` downloads
- documented the remaining `npm audit` state in `docs/VALIDATION_SYSTEM.md` and
  `scripts/README.md`: 3 moderate findings still flow through
  `markdownlint-cli2` (`js-yaml@4.1.1` and `markdown-it@14.1.1`) and must be
  revisited when upstream updates its dependency graph

---

## 2026-06-25 - Drop Preview Nginx Deprecation Warnings

**Fixed:**

- updated `scripts/polyscope-rollout.py` so generated preview nginx config now uses `http2 on;` with plain `listen ... ssl;` directives by default instead of the deprecated `listen ... http2` syntax, while `--install-nginx` auto-detects the local nginx version and keeps the legacy listen-level fallback for nginx older than 1.25.1
- removed redundant `ssi_types text/html;` from the generated SSI-only preview locations because `text/html` is already enabled by default, eliminating the duplicate MIME-type warning during `nginx -t`
- extended `tests/polyscope-rollout.sh` so preview rollout regressions now fail if the modern render path reintroduces deprecated `http2` listen syntax, the nginx 1.24 fallback drops listen-level HTTP/2, or the redundant SSI MIME override reappears

---

## 2026-06-25 - Harden Polyscope Preview CSP Rollout

**Fixed:**

- updated `scripts/polyscope-rollout.py` so generated frontend Polyscope workspaces now expose a dedicated `npm run test:preview:pwa-headers` smoke command, making the live preview CSP contract easy to verify immediately after rollout
- tightened generated preview nginx config to derive a per-request preview nonce, scope SSI nonce expansion to frontend preview HTML routes, and emit the nonce-aware `style-src-elem` policy current frontend workspaces require instead of the older inline-style preview CSP
- aligned `tests/polyscope-rollout.sh` with the hardened preview CSP contract so rollout regressions now fail if generated nginx or generated frontend workspace metadata drifts back to the older preview policy

---

## 2026-06-23 - Harden Polyscope Preview Publishing

**Fixed:**

- updated `scripts/polyscope-rollout.py` so staged frontend preview publishes remove stale files from `dist/`, handle file/directory shape changes, and still publish `index.html` last after assets are reconciled
- rejected symlinked staged build output and symlinked live preview `dist/` paths before publishing
- kept preview nginx compatible with nginx 1.24, relaxed preview CSP for static framework output, revalidated `/assets/`, and denied hidden/PHP files below immutable asset prefixes
- added Python bytecode ignore rules to `.gitignore` so generated `__pycache__/` artifacts do not enter future rollout diffs

---

## 2026-06-21 - Standardize Site Terminology For Customer Locations

**Added:**

- added `docs/brand/terminology.md` to define the approved customer-location domain terminology: English uses `site`/`sites`, German domain copy may use `Objekt`/`Objekte`, and `object` remains reserved for technical contexts

**Changed:**

- linked `docs/brand/naming.md` and `docs/brand/README.md` to the new terminology standard so naming and public-copy guidance point to a single source of truth
- aligned `docs/feature-requirements.md` to use `site` terminology consistently in English domain copy, while keeping historical issue titles explicitly marked as historical
- added an editorial note and summary cleanup in `docs/adr/20251126-organizational-structure-hierarchy.md` so preserved historical `object` wording cannot be mistaken for current repository terminology

---

## 2026-06-18 - Fix Linked Polyscope Preview URLs

**Fixed:**

- updated `scripts/polyscope-rollout.py` so frontend and API preview configuration resolves linked worktree names from Polyscope `worktree_links` instead of assuming every linked repository uses the same workspace folder name. This keeps asymmetric linked previews such as `frontend-azure-cheetah` and `api-azure-cheetah-165552b7` wired to each other correctly.
- changed generated frontend preview setup, build, watch, and workspace Playwright commands to target the linked API worktree host when one exists, with the current folder name retained as the fallback for unlinked workspaces.
- changed API preview `.env` preparation to allow the linked frontend worktree origin in `FRONTEND_URL`, `SANCTUM_STATEFUL_DOMAINS`, and `CORS_ALLOWED_ORIGINS`, while keeping the API workspace host based on its own worktree name.
- hardened generated Polyscope review, PR, draft-PR, merge, push-and-merge, and task prompts for every managed repository with an explicit rule forbidding AI agent attribution, AI tool labels such as Codex/Copilot/Cursor, `[codex]` prefixes, and AI `Co-authored-by` trailers in GitHub-facing content.

**Added:**

- extended `tests/polyscope-rollout.sh` with an asymmetric linked-worktree regression that proves a frontend workspace can target a suffixed API workspace and the API can allow the unsuffixed frontend origin.
- extended `tests/polyscope-rollout.sh` to assert that generated Polyscope repository prompts and task prompts for all managed repositories include the no-AI-attribution rule.
- extended `tests/polyscope-rollout.sh` with resolver probe tests for `build_frontend_preview_build_command` and `build_frontend_preview_playwright_command` confirming the linked API workspace name is resolved correctly for both commands.
- extended `tests/polyscope-rollout.sh` with a CLI-path test that invokes `--prepare-api-worktree` with `POLYSCOPE_DB_PATH` set and asserts `FRONTEND_URL` is resolved from the linked worktree, validating the `parse_args()` env-var fallback for `--db-path`.

## 2026-06-14 - Document SecPal Brand And Shared Design Standards

**Added:**

- introduced `docs/brand/` with the SecPal and GuardGuide brand architecture, naming, slogans, footer wording, logo usage, and licensing wording standards, plus a section README that documents the brand scope boundary between this organization-wide repository and the owning product repositories
- introduced `docs/design/` with shared standards for typography, color usage, dark mode, page titles, layout, navigation, components, forms, tables, and accessibility, plus a section README that documents the design scope boundary between organization-wide guidance and product-repository implementation
- added a domain-prefixed brand ADR series (BRAND-0001 brand architecture, BRAND-0002 typography, BRAND-0003 navigation pattern, BRAND-0004 footer wording, BRAND-0005 page titles, BRAND-0006 app UI stack ownership) using a `BRAND-NNNN-` filename prefix to avoid collisions with the existing date-prefixed `ADR-NNN` series; linked all six from `docs/adr/README.md` and documented the domain-prefix naming exception alongside the existing convention
- documented the canonical two-line public AGPL footer in `docs/brand/footer-wording.md`, `docs/brand/brand-architecture.md`, and `docs/adr/BRAND-0004-footer-wording.md`: line 1 is `Powered by <Product> – <Slogan>` linked to the brand's homepage, with each surface using its own `Powered by <own brand>` self-attribution; line 2 is `AGPL v3+ | <Source Code label>` with `AGPL v3+` linked to the canonical public AGPL URL and the Source Code label linked to the surface's own canonical public source repository
- documented the per-surface Source Code link-target rule with worked examples for every managed SecPal/GuardGuide surface — `SecPal` platform/suite uses the SecPal GitHub organization, `secpal.app`/`changelog`/`guardguide.de` marketing surfaces each link to their own dedicated repository, and the GuardGuide product app links to `SecPal/GuardGuide` — so the AGPL source-attribution purpose is preserved instead of all surfaces pointing at the same product repository
- documented the brand-plus-slogan en-dash separator rule (`–` U+2013 with one space on each side) and the line-2 license/source-code separator rule (`|` U+007C with one space on each side) in `docs/brand/slogans.md`, `docs/brand/footer-wording.md`, and `docs/adr/BRAND-0004-footer-wording.md`, with explicit incorrect examples for hyphen-minus (`-` U+002D), em dash (`—` U+2014), and substitute separators (`/`, `·`, `•`, `,`, space-only gap)
- documented the public AGPL link-target scope in `docs/brand/licensing-wording.md`: the canonical URL `https://www.gnu.org/licenses/agpl-3.0.html` is used in product brand footers and in policy documents that need an authoritative external anchor (such as `CLA.md`), while repository READMEs and in-repo "License" sections link to the local `LICENSE` file or `LICENSES/AGPL-3.0-or-later.txt`, and SPDX headers and package metadata use the URL-free SPDX expression `AGPL-3.0-or-later`
- documented that the slogan, the `Powered by` prefix, the brand name, and the `AGPL v3+` label remain English on every surface and locale (including German-language pages); the Source Code label is localized using the canonical local term for "source code" (English `Source Code`, German `Quellcode`, canonical local term in other locales), and abbreviated or informal forms such as `Source`, `Quelle`, or `Quelltext` are not allowed
- documented that icons on line 2 are an optional product-level visual addition; the `.github` text standard remains the source of truth so plain-text README footers, generated PDFs, and screen-reader transcripts render the same canonical strings
- documented in `docs/brand/slogans.md` that the compact lockup uses the short form `GuardGuide` once the relationship is established, while body copy first mentions still use the full `GuardGuide by SecPal` name per `docs/brand/naming.md`
- added `.context/` to `.gitignore` so the Polyscope per-workspace agent scratch directory is excluded from version control and REUSE coverage

---

## 2026-06-15 - Reprovision Polyscope Worktrees On Lockfile Drift

**Changed:**

- updated `scripts/polyscope-rollout.py` so Node-based managed worktrees now run plain `npm ci` during provisioning instead of `test -d node_modules || npm ci`. Provisioning is already marker-gated, so the old existence check only preserved stale dependency trees after lockfile changes.
- updated `scripts/polyscope-rollout.py` so the per-worktree provision marker hash now includes dependency manifest inputs (`package.json`, `package-lock.json`, `composer.json`, `composer.lock`) in addition to the setup command list. Together with unconditional `npm ci`, this forces a fresh dependency install when a managed workspace's lockfiles change, closing the drift that left GuardGuide preview worktrees with stale `node_modules` after the new `@fontsource/inter` dependency landed.

**Added:**

- extended `tests/polyscope-rollout.sh` with a regression that mutates a provisioned frontend worktree `package-lock.json` and proves the next provisioning pass reruns setup instead of trusting the previous marker.

---

## 2026-06-14 - Skip Gitignored Agent Scratch Dir In `check-domains.sh`

**Changed:**

- taught `scripts/check-domains.sh` to skip the gitignored agent scratch directory `.context/` by adding `--exclude-dir=".context"` alongside the existing `.git`, `node_modules`, and `vendor` exclusions. The exclusion applies at every directory depth. Polyscope-managed workspaces use `.context/` to pass throwaway files between agents and the `gh` CLI (PR body drafts, scratch notes, etc.) which are never tracked and never reach CI, so the local gate now mirrors what CI actually sees instead of failing on prose that quotes forbidden `secpal.*` hosts verbatim.
- hardened `scripts/check-domains.sh` with a tracking-aware guard that runs before the grep scan: inside a git workspace the script lists every tracked path under `.context/` via `git ls-files` and fails loudly when any exist, so a `git add --force` on `.context/forced.md` can no longer slip past the gate by riding on the directory-name exclusion. Together with `--exclude-dir=".context"` this closes the local/CI divergence Codex flagged on SecPal/.github#489 (`scripts/check-domains.sh:59`).
- documented the new `.context/` exclusion plus the tracking-aware guard in `scripts/README.md` under the existing `check-domains.sh` "Scope (intentional limit)" section so contributors discover both layers alongside the existing dependency-directory exclusions.
- refined the `.context` entry added to `.gitignore` by the brand-and-design-standards change to `.context/` (directory-only, trailing slash) so the rule matches only the Polyscope agent scratch directory and cannot accidentally ignore a file named `.context`.

**Added:**

- extended `tests/check-domains.sh` with a regression fixture (check 6) that proves the gate ignores an unapproved host stashed inside `.context/notes.md` (positive case, `.context/` cleaned up before the next subcase) while still failing on the same string in a tracked-equivalent location at the workspace root (negative case). The two subcases are now fully isolated so neither can mask the other.
- added a check-7 regression fixture in `tests/check-domains.sh` that boots a throwaway `git init` workspace, force-adds `.context/forced.md` with an unapproved host, and asserts the gate exits non-zero and surfaces the tracked path — proving the tracking-aware guard closes the `--exclude-dir` bypass on SecPal/.github#489. A paired clean-workspace assertion confirms the guard is scoped to `.context/` and does not regress the happy path on git workspaces without tracked scratch content.
- hardened the test's temp-directory cleanup: a single `cleanup()` function is registered on EXIT with empty- and existence-guarded `rm -rf` calls so an early-assertion exit can no longer fire `rm -rf ""` errors and mask real failure output.
- modernized the guardguide grep assertion to use `grep -E '|...|'` (POSIX extended regex) instead of the GNU-only `\|` alternation, so the test is portable to BSD/macOS grep (see SecPal/.github#489).

---

## 2026-06-14 - Align `check-domains.sh` Banner With Its `secpal.*` Scope

**Changed:**

- rewrote the banner and on-failure Policy block in `scripts/check-domains.sh` so the help text matches the script's actual `secpal\.[A-Za-z0-9.-]+` match regex: the gate explicitly documents that it only enforces the `secpal.*` namespace split, drops the misleading "ANY other" claim in favour of "any other unapproved `secpal.*` host", and points readers at the owning repository's policy guards for non-`secpal` SecPal hosts such as `guardguide.de` (introduced in SecPal/.github#483).
- documented `scripts/check-domains.sh` in `scripts/README.md` with an explicit "Scope (intentional limit)" section so contributors discover the boundary alongside the other validation scripts and stop expecting the org-wide gate to police every external SecPal domain.

**Added:**

- added `tests/check-domains.sh` regression test that locks in the banner/README scope language, exercises a synthetic workspace to prove `guardguide.de` references pass cleanly, and proves an unapproved `secpal.*` host (one is staged inside the test's own temporary workspace, never in the repo) still fails the gate, and wired it into `scripts/preflight.sh` so the contradiction surfaced on SecPal/.github#483 (resolved as out of scope and tracked in SecPal/.github#484) cannot return unnoticed.

---

## 2026-06-14 - Soft-Warn Missing Repos In `setup-hooks.sh`

**Changed:**

- reworked `setup-hooks.sh` so a missing managed repository directory is reported as a warning (`Skipped (missing directory)` summary line) instead of being added to `FAILED_REPOS`, and the script now exits `0` when every present repo's pre-push, pre-commit, and commit-msg hooks installed cleanly — only real installation step failures still exit `1`. The summary now points users at `.github/scripts/install-polyscope-rollout.sh`, matching the actual workspace layout, and still treats non-directory managed paths as hard failures so corrupted workspaces do not slip through as success.
- documented the new soft-warn contract and the rollout sync command in `scripts/README.md` so the `setup-hooks.sh` and `install-polyscope-rollout.sh` flows are discoverable side-by-side.

**Added:**

- expanded `tests/setup-hooks.sh` from a single happy-path assertion into four regression scenarios — happy path, warning path (missing managed repo still exits `0` with the correct rollout hint), corrupt-path failure path (managed repo path exists but is not a directory), and failure path (broken `setup-pre-push.sh` still exits `1`) — and wired the test into `scripts/preflight.sh` so the soft-warn contract from SecPal/.github#485 cannot regress unnoticed.

---

## 2026-06-14 - Bootstrap guardguide.de Rollout

**Added:**

- registered `guardguide.de` in `scripts/polyscope-rollout.py` as a static Astro site with its own copilot instructions, preview prefix `guardguide-de`, autostarted Build Watch, and an All Checks command so Polyscope workspaces for the marketing site come up with the same governance and preview tooling as the other managed repositories
- extended generated nginx preview routing in `scripts/polyscope-rollout.py` to recognize the `guardguide-de` host prefix and serve the built Astro `dist/` output, with the generic preview precedence updated so `changelog > guardguide.de > secpal.app > frontend > api` still resolves deterministically
- added `guardguide.de` to the managed required-checks baseline in `scripts/sync-required-checks.sh` (Astro check/build plus Node tests), the hook installation coverage in `setup-hooks.sh`, the epic audit repo list in `scripts/audit-closed-epics.sh`, and the Polyscope installer watch list in `scripts/install-polyscope-rollout.sh`
- extended `tests/polyscope-rollout.sh`, `tests/sync-required-checks.sh`, and `tests/setup-hooks.sh` to prove the generated rollout output, branch-protection payload, and hook installation coverage all include the new repository

**Fixed:**

- rewrote the `CREATED`, `UPDATED`, and `SKIPPED` counter increments in `scripts/sync-labels.sh` from `((COUNTER++))` to `COUNTER=$((COUNTER + 1))` so label sync no longer exits early under `set -e` when a counter is incremented from `0` (post-increment of `0` returns `0`, which `set -e` treats as a failed command)
- taught the generic static preview watcher in `scripts/polyscope-rollout.py` to ignore explicit generated files, and configured the `secpal.app` and `guardguide.de` Build Watch commands to skip their generated `public/og-*.svg` and `public/og-*.png` assets so `npm run build` no longer retriggers the watcher indefinitely by rewriting files inside the watched `public/` tree

---

## 2026-06-13 - Fix Polyscope Preview Build Watchers

**Fixed:**

- replaced the generated GuardGuide Polyscope `Vite Dev` action with an autostarted full-build watcher so nginx-backed previews keep `public/build` current without depending on the Vite dev server or hot-file behavior
- added matching full-build watchers for the generated `secpal.app` and `changelog` Polyscope configs so static preview hosts rebuild their served output after source changes instead of relying on a one-time setup build
- extended `tests/polyscope-rollout.sh` to reject GuardGuide `npm run dev` preview actions and to prove the generated static and GuardGuide preview configs include the build watcher commands

---

## 2026-06-13 - Fix Dependabot Auto-Merge Gating To Use PR Author

**Fixed:**

- updated `.github/workflows/dependabot-auto-merge.yml` and `.github/workflows/reusable-dependabot-auto-merge.yml` to gate on `github.event.pull_request.user.login == 'dependabot[bot]'` instead of `github.actor`, so maintainer-triggered `reopened` and `ready_for_review` events on Dependabot-authored PRs no longer skip auto-merge enrollment
- extended `tests/dependabot-auto-merge.sh` to assert the PR-author-based invariant across both the caller and reusable workflows and to fail loudly if either workflow regresses to the brittle `github.actor` gate

---

## 2026-06-13 - Fix GuardGuide Polyscope Preview Routing

**Fixed:**

- updated `scripts/polyscope-rollout.py` so generated preview nginx config routes Laravel preview workspaces through a neutral `secpal-preview` PHP-FPM socket instead of the API-specific pool, preventing GuardGuide previews from inheriting API runtime assumptions
- increased generated FastCGI response-header buffers for preview PHP routes so GuardGuide login pages with Inertia preload links and encrypted Laravel cookies no longer fail with `upstream sent too big header`
- kept GuardGuide repository links to `api`, `frontend`, `contracts`, and `android` in the managed Polyscope metadata so future rollout syncs preserve the intended cross-workspace context
- removed the stale frontend `test:e2e:staging` run action from generated Polyscope configs so `polyscope-rollout-sync.service` no longer fails validation before writing updated workspace metadata
- made generated GuardGuide preview seeding idempotent by seeding the access catalog directly and normalizing the preview test user instead of re-running the non-idempotent local `DatabaseSeeder`
- extended `tests/polyscope-rollout.sh` to prove the generated nginx route, GuardGuide repository links, and rollout summary stay aligned

---

## 2026-06-06 - Add Local Polyscope State Audit Guard

**Added:**

- added `scripts/audit-polyscope-state.py` to audit the local Polyscope runtime for clone-root drift, unregistered Git worktrees, invalid stub directories, clone-local config hygiene, and over-retained `polyscope.db` backups
- added `tests/polyscope-state-audit.sh` plus a `scripts/preflight.sh` hook so the local Polyscope audit stays regression-tested with fixture-backed SQLite and filesystem coverage
- documented the new audit script in `scripts/README.md` so the operational cleanup path no longer depends on ad hoc one-off shell commands

---

## 2026-06-05 - Codify Required Branch Protection Checks

**Added:**

- added `scripts/sync-required-checks.sh` so the SecPal application repositories, the org defaults repository itself, and `GuardGuide` now have a single manifest-backed way to print or apply the intended required status-check payloads instead of relying on ad hoc GitHub API calls
- added `tests/sync-required-checks.sh` and hooked it into `scripts/preflight.sh` so required-check drift is caught locally before branch-protection guidance or workflow names change again
- updated `docs/ghas-setup.md` and `scripts/README.md` so the documented branch-protection path now points at the repo-specific sync flow rather than the stale one-size-fits-all `CodeQL` example

**Changed:**

- removed the duplicate inline REUSE and license-compatibility jobs from `.github/workflows/quality.yml` so those required checks are reported only by their dedicated workflows

---

## 2026-06-04 - Seed GuardGuide During Polyscope Preview Setup

**Fixed:**

- updated `scripts/polyscope-rollout.py` so GuardGuide preview setup now runs `php artisan db:seed --force` after migrations, matching the explicit request that newly created GuardGuide Polyscope workspaces come up with seeded local/testing data instead of schema-only state
- extended `tests/polyscope-rollout.sh` so the rollout regression now proves both the generated GuardGuide `polyscope.local.json` setup commands and the real GuardGuide worktree provisioning path include the seed step

---

## 2026-06-04 - Align GuardGuide Polyscope Rollout With The Laravel Monolith

**Fixed:**

- updated `scripts/polyscope-rollout.py` so GuardGuide now emits the current shadcn/ui instruction path, check-only validation commands, a preview `APP_URL` rewrite during setup, a required frontend build step, and the real current run actions (`Pest`, `Typecheck`, `Build`, `Vite Dev`) instead of stale Catalyst/Vitest-era commands
- fixed the GuardGuide preview environment helper to generate a worktree-safe inline Python command without leading indentation, preventing `--provision-worktrees` from failing with `IndentationError` while rewriting `.env`
- extended `tests/polyscope-rollout.sh` so the rollout regression suite now proves the renamed GuardGuide instruction file, current validation/run command surface, preview `APP_URL` rewrite, and successful GuardGuide worktree provisioning

---

## 2026-06-03 - Continue Polyscope Provisioning After Workspace Failures

**Fixed:**

- updated `scripts/polyscope-rollout.py` so `--provision-worktrees` now isolates expected per-worktree provisioning failures, records them under `failed_provision_worktrees` in the rollout summary, continues provisioning the remaining managed workspaces instead of aborting the entire run on the first broken clone, and keeps preview database/schema targets for still-present but broken API clones out of cleanup
- extended `tests/polyscope-rollout.sh` with regressions where one API workspace setup fails, a malformed API clone must still protect its preview storage targets from cleanup, and a fresh GuardGuide workspace must still provision successfully, proving the shared rollout path no longer lets unrelated workspace failures block newer repositories or delete live preview data for broken clones

---

## 2026-06-03 - Fix Polyscope Server SSH Agent Socket For Worktree Creation

**Fixed:**

- updated `scripts/install-polyscope-rollout.sh` so the system-scope `polyscope-server.service` override resolves `SSH_AUTH_SOCK` to the actual service user's runtime directory instead of writing the broken literal `%U` placeholder that expands to `/run/user/0/openssh_agent` at runtime
- extended `tests/polyscope-rollout.sh` so the installer regression suite now proves both the resolved numeric runtime socket path for an explicit system service user and the root fallback when the unit omits `User=`, preventing future regressions in API-driven worktree creation

---

## 2026-06-03 - Register GuardGuide In Polyscope Rollout

**Changed:**

- added `GuardGuide` to `scripts/polyscope-rollout.py` so the rollout generator now manages its repository prompts, local Polyscope config, and preview URL alongside the existing SecPal repos
- configured GuardGuide as a Laravel monolith with React/Catalyst guidance, combined repo-local validation commands, and a prefixed preview host at `guardguide-<workspace>.preview.secpal.dev`
- extended the generated preview nginx mapping and `tests/polyscope-rollout.sh` so GuardGuide registration, local config rendering, and prefixed preview routing stay regression-covered

---

## 2026-05-16 - Add Polyscope Run Controls For Checks And Findings

**Changed:**

- updated `scripts/polyscope-rollout.py` so generated `polyscope.local.json` files now expose repo-specific `All Checks` run actions across the SecPal workspace instead of requiring developers to remember the underlying validation commands manually
- surfaced `Preflight` as a run action wherever a repository ships `scripts/preflight.sh`, making the existing preflight entrypoint available on demand from Polyscope instead of only through hooks or manual shell use
- added a standard `Fix current findings` Polyscope task that tells the agent to run the current repo's checks, fix repo-local findings, rerun validations, and stop instead of widening the branch into unrelated multi-topic cleanup
- extended `tests/polyscope-rollout.sh` so the rollout generator must keep emitting those run actions and the fix-findings task for every supported repository
- tracked as [#457](https://github.com/SecPal/.github/issues/457)

---

## 2026-05-16 - Reprovision Drifted Polyscope API Preview Targets

**Fixed:**

- updated `scripts/polyscope-rollout.py` so API worktree provisioning normalizes the preview `.env` before honoring the provision marker, instead of treating a matching `setup_hash` as sufficient even when the worktree's preview target has drifted
- stored the API preview storage target in `.polyscope-secpal-provisioned.json`, which makes older markers trigger a one-time re-provision pass and prevents stale markers from suppressing schema/database recovery for a renamed or drifted worktree
- extended `tests/polyscope-rollout.sh` with a schema-mode regression that mutates an existing API worktree back to a sibling preview schema and proves the next provisioning run repairs the `.env` and reruns the API setup commands
- tracked as [#455](https://github.com/SecPal/.github/issues/455)

---

## 2026-05-16 - Make Polyscope Metadata Sync Idempotent

**Fixed:**

- updated `scripts/polyscope-rollout.py` so `sync_repository_metadata()` now compares the desired repository prompts and managed `repository_links` against the current `polyscope.db` state before taking a backup or writing any rows
- skipped both `backup_db()` and SQLite writes when the repository metadata is already up to date, eliminating the `polyscope-worktree-provision.path` feedback loop that was caused by no-op DB rewrites triggering fresh inotify activations
- extended `tests/polyscope-rollout.sh` to prove a repeated identical metadata sync leaves `polyscope.db` unchanged and reports `db_backup: null` on the second run
- tracked as [#453](https://github.com/SecPal/.github/issues/453)

---

## 2026-05-16 - Restore DB Sync For Polyscope Worktree Provisioning

**Changed:**

- removed `--skip-db-sync` from the generated `polyscope-worktree-provision.service` so automatic Polyscope provisioning now reapplies repository prompt and review metadata instead of leaving AI instruction settings drifted after repo deletion or re-registration
- kept `--skip-local-configs` in place so the background provisioner still avoids rewriting repo-local workspace config during its repair pass
- added `StartLimitIntervalSec=300` / `StartLimitBurst=3` to the provisioner service unit to bound the self-trigger feedback loop (DB sync writes to `polyscope.db` which the path unit watches)

---

## 2026-05-14 - Harden `gh pr create` examples with tmpfile trap

**Changed:**

- replaced bare `rm -f "$tmpfile"` after `gh pr create` with `trap 'rm -f "$tmpfile"' EXIT`
  in the workflow documentation snippets (`README.md`, `docs/workflows/PROJECT_AUTOMATION.md`,
  `docs/workflows/QUICK_REFERENCE.md` including the signed-commit remediation block,
  `docs/workflows/ROLLOUT_GUIDE.md`) so the temp file is cleaned up even when the command
  fails or the shell is interrupted
- switched inline `--body` on `gh pr create` to `--body-file` for programmatic examples,
  matching Issue And PR Discipline in `.github/copilot-instructions.md`
- tracked as [#441](https://github.com/SecPal/.github/issues/441)

---

## 2026-05-14 - Allow ODbL-1.0 in Reusable License Compatibility

**Changed:**

- allowed `ODbL-1.0` in `reusable-license-compatibility.yml` so `reuse spdx` output that includes the Open
  Database License (bundled upstream license texts, SPDX on data or fixture files, and related metadata)
  passes the centralized compatibility job; scope is documented inline and does not endorse ODbL as the
  default license for application source
- set `permissions: contents: read` on the reusable workflow (least privilege for `workflow_call`)
- clarified the ODbL-1.0 inline comment to truthfully state that the check verifies AGPL compatibility only
  and that file-level usage appropriateness is a code-review concern, resolving the mismatch flagged by
  Copilot review (comment previously implied path-aware enforcement that CI did not implement)
- added `tests/license-compatibility.sh` with positive and negative regression fixtures for the allowlist,
  wired into `scripts/preflight.sh` so future edits to the compatible-licenses array are caught locally
- tracked as [#449](https://github.com/SecPal/.github/issues/449)

---

## 2026-05-09 - Harden API Preview Runtime Recovery

**Changed:**

- updated `scripts/polyscope-rollout.py` so generated API preview `Queue Worker` commands now run
  `php artisan queue:work --queue=activity-hash-chain,merkle,opentimestamp,default --sleep=3 --tries=3 --max-time=3600`
  instead of `queue:listen`, keeping default mail jobs and forensics jobs on one explicit worker path that
  can satisfy the readiness heartbeat checks consistently across preview workspaces
- updated the generated API preview `Preview Only: Refresh DB + E2E User` command to rerun the same
  hardened `config:clear`, migration, `db:seed`, and canonical `test@example.com` normalization flow as
  initial setup instead of relying on raw `migrate:fresh --seed`, so missing tenant keys and the standard
  preview login are restored together after preview DB resets
- extended `tests/polyscope-rollout.sh` to prove API preview configs emit the combined `queue:work`
  command, reject the old `queue:listen` worker, and use the hardened reseed flow for preview DB refreshes

## 2026-05-09 - Replace Fragile Frontend Preview Watch Builds With Full Rebuild Watcher

**Fixed:**

- replaced the frontend Polyscope preview `Build Watch` command with a stable full-rebuild watcher
  that reruns `npm run build -- --mode preview` after source changes instead of relying on
  `vite build --watch --mode preview`, which could stop permanently after repeated locale or UI
  edits with `vite:css-post` / unknown-file failures

## 2026-05-09 - Pin Preview Frontend Local Env Overrides To Workspace API Hosts

**Changed:**

- hardened `scripts/polyscope-rollout.py` so frontend preview provisioning now rewrites `.env.local`, `.env.preview.local`, and `.env.production.local` inside preview worktrees to the workspace-specific preview API host instead of leaving later builds free to fall back to `api.secpal.dev`
- extended `tests/polyscope-rollout.sh` to prove frontend preview provisioning overwrites live-targeted preview and production local Vite API overrides with the current workspace preview API host

## 2026-05-09 - Fix AI-Trailer Hook Robustness and Validator Misdetection

**Fixed:**

- `scripts/strip-ai-trailers.sh`: use `mktemp "${TMPDIR:-/tmp}/strip-ai-trailers.XXXXXX"` for portability
  on BSD/macOS; replace the awk that collapsed all consecutive blank lines with a
  trailing-only blank-line trimmer that preserves intentional blank lines in the commit body
- `setup-hooks.sh`: resolve the hooks directory via `git rev-parse --git-path hooks`
  instead of hardcoding `.git/hooks`, so the `commit-msg` hook installs correctly in
  Git worktrees where `.git` is a `gitdir:` pointer file rather than a directory
- `scripts/validate-copilot-instructions.sh`: `detect_repo_type()` now checks
  for `workflow-templates/` directory before the openapi-in-package.json check,
  so the `.github` org repository is correctly identified as `org` instead of
  `contracts`

---

## 2026-05-09 - Strip AI Agent Attribution From Commits and PRs

**Added:**

- added `scripts/strip-ai-trailers.sh`, a `commit-msg` hook that removes
  `Co-authored-by:` trailers injected by AI coding agents (Cursor, GitHub
  Copilot) while preserving human co-author and dependabot trailers
- Polyscope provisioning now installs the `commit-msg` hook as a symlink in
  every managed worktree alongside the existing pre-commit and pre-push hooks
- `setup-hooks.sh` installs the `commit-msg` hook in all SecPal repositories
  as part of the local development environment setup

**Changed:**

- disabled `attributeCommitsToAgent` and `attributePRsToAgent` in the Cursor
  CLI configuration so AI-generated attribution trailers are not added at the
  source
- hardened the no-AI-attribution policy in `.github/copilot-instructions.md`
  with an explicit rule and a reference to the enforcement hook

## 2026-05-09 - Skip Invalid Polyscope Stub Directories During Provisioning

**Changed:**

- hardened `scripts/polyscope-rollout.py` so automatic worktree provisioning now skips clone-root stub directories that are missing the real repo structure required for provisioning instead of trying to sync local config, install hooks, or run setup commands inside them
- taught API preview-storage cleanup to ignore those invalid stub directories too, so orphaned preview databases are no longer kept alive just because a broken `fix` or `feat` directory exists under the clone root
- extended `tests/polyscope-rollout.sh` to prove valid worktrees still provision normally when invalid stub directories are present, and to verify stale preview databases for those invalid stubs are cleaned on the next provisioning pass

## 2026-05-09 - Align ADR-010 Retention Terminology With Current Backend Model

**Changed:**

- updated `docs/adr/20251221-activity-logging-audit-trail-strategy.md` to describe legal retention windows per `log_name` instead of the superseded security-level matrix
- aligned ADR-010 archival examples with the current calendar-year cutoff, hash-only archive, and orphaned-genesis retention flow documented in the backend runtime

## 2026-05-09 - Document Signed-Commit Deadlock Remediation For Legacy PR Branches

**Changed:**

- updated `docs/workflows/QUICK_REFERENCE.md` with the supported replacement-PR flow when signed-commit enforcement blocks a legacy branch with unsigned history
- documented that the policy-safe path is to supersede the blocked PR from a fresh signed branch instead of force-pushing or bypassing branch protection

## 2026-05-08 - Require PR Evidence For TDD Or Explicit Non-Executable Changes

**Changed:**

- added `scripts/validate-pull-request-evidence.sh`, `tests/pull-request-evidence.sh`, and `.github/workflows/pull-request-evidence.yml` so `.github` pull requests now fail fast when the body omits concrete fail-first evidence or an explicit no-executable-change reason
- updated `.github/pull_request_template.md` and `docs/workflows/QUICK_REFERENCE.md` with a dedicated `TDD / Validate-First Evidence` section that keeps validate-first exceptions tied to repository instructions instead of leaving them implicit
- wired the new regression test into `scripts/preflight.sh` so local governance checks catch PR-evidence drift before a branch is pushed

## 2026-05-08 - Block Obvious German PR Titles And Bodies In .github

**Changed:**

- added `scripts/validate-pull-request-english.sh`, `tests/pull-request-english.sh`, and `.github/workflows/pull-request-english.yml` so `.github` pull requests now fail when their title or author-written body contains obvious German markers instead of English GitHub-facing communication
- wired the new language regression test into `scripts/preflight.sh` so local governance checks catch PR-language guardrail drift before push time
- updated `.github/pull_request_template.md` and `docs/workflows/QUICK_REFERENCE.md` to tell authors that PR titles and author-written bodies must be in English, while comments and review text remain reviewer-enforced until a narrower follow-up strategy is proven

## 2026-05-08 - Enforce Signed PR Commits In .github

**Changed:**

- added `scripts/validate-pull-request-commit-signatures.sh`, `tests/pull-request-commit-signatures.sh`, and `.github/workflows/pull-request-commit-signatures.yml` so `.github` pull requests now fail when any branch commit is not GitHub-verified as signed
- wired the new signed-commit regression test into `scripts/preflight.sh` so local governance checks catch validator or workflow drift before push time
- hardened the signed-commit regression test to use portable `mktemp -d "${TMPDIR:-/tmp}/pull-request-commit-signatures.XXXXXX"` temp directories, so current `.github` branches and local preflight stay valid on stricter `mktemp` implementations too
- documented in `docs/workflows/QUICK_REFERENCE.md` that signed commit verification is now CI-enforced while English-only GitHub communication remains reviewer-enforced until a narrower, low-noise lint strategy is proven

## 2026-05-03 - Isolate Polyscope Preview Storage Per API Workspace

**Changed:**

- updated `scripts/polyscope-rollout.py` so API worktree preparation now isolates PostgreSQL preview storage per workspace: when the role can create databases it provisions a deterministic preview database, and when it cannot it falls back to a deterministic preview schema wired through `DB_URL?search_path=...`; in both cases the original shared base database is persisted in `POLYSCOPE_BASE_DB_DATABASE`, so a fresh `frontend-<workspace>.preview.secpal.dev` no longer shares mutable API data with other preview workspaces by default
- taught the worktree provisioner to prune orphaned API preview storage targets when the matching Polyscope workspace directory disappears, dropping stale preview databases or schemas as appropriate so repeated provisioning stays idempotent without accumulating abandoned preview state on the host
- changed the generated API `polyscope.local.json` setup to call the shared rollout helper directly for worktree preparation, so manual Polyscope setup and automatic `--provision-worktrees` runs use the same database-isolation path instead of drifting between inline env rewrites and background provisioning behavior
- extended `tests/polyscope-rollout.sh` to prove both workspace-specific preview-database provisioning and schema fallback, tracked base-database metadata, cleanup of removed workspaces, and idempotent reruns after cleanup

## 2026-05-03 - Respect System-Managed Polyscope Server Installs

**Changed:**

- hardened `scripts/install-polyscope-rollout.sh` to auto-detect an existing system-managed `polyscope-server.service` and install a SecPal runtime drop-in there instead of blindly creating a competing user `polyscope-server.service`, so repeated rollout installs no longer reintroduce port-4321 restart loops on hosts where Polyscope already runs as a system service
- kept the user-managed rollout sync and worktree-provision path units, but decoupled them from the user server unit when the system service is authoritative, so prompt sync and fresh-workspace provisioning still run immediately after install without reviving the conflicting user server path
- made Expose wrapper installation idempotent when `expose-linux-x64.real` already exists and the live `expose-linux-x64` path has been restored to the original binary contents, so re-running the installer repairs the wrapper instead of aborting on a stale-but-safe backup state
- extended `tests/polyscope-rollout.sh` to cover both the repaired Expose rewrap path and the auto-detected system-service install path, including generated drop-in content and the absence of a competing user Polyscope server unit

## 2026-05-02 - Return Direct Preview URLs From Polyscope Share

**Changed:**

- added `scripts/polyscope-expose-wrapper.sh` and taught `scripts/install-polyscope-rollout.sh` to install it as the live `~/.polyscope/bin/expose-linux-x64` entrypoint with `expose-linux-x64.real` kept as the fallback binary, so Polyscope `tunnel.start` now returns the existing `https://*.preview.secpal.dev` URL directly for SecPal preview hosts instead of handing browser-share links off to the unreliable free `sharedwithexpose.com` edge
- restored repo-prefixed canonical preview hosts in generated Polyscope config for preview-capable repositories (`api-`, `frontend-`, `secpal-app-`, `changelog-`), and aligned the API preview `FRONTEND_URL` rewrite with `frontend-<workspace>.preview.secpal.dev`, so shared/opened preview URLs now keep the repository type in front of the workspace name instead of collapsing back to the generic host alias
- taught `scripts/polyscope-rollout.py` to heal API worktrees missing `.env` by copying the source preview environment from the primary `api` checkout before applying workspace-specific rewrites, and to skip cleanly with a journal-visible message if no source preview env exists, so stale clones no longer fail `polyscope-worktree-provision.service`
- added `scripts/polyscope-git-wrapper.sh` and wired the Polyscope systemd units to a dedicated PATH layer plus explicit `SSH_AUTH_SOCK`, so Polyscope-driven `git commit` calls now force `-S` through the configured SSH signing key instead of depending on the agent's internal commit path honoring repo config
- kept non-SecPal or non-preview Expose calls on the original binary path, so the share override stays narrowly scoped to the already-public SecPal preview domain rather than replacing Expose globally
- extended `tests/polyscope-rollout.sh` to cover API env healing for stale worktrees, git-wrapper installation and signed-commit enforcement, preview-domain short-circuiting, and fallback execution for non-preview hosts

## 2026-05-02 - Auto-Provision Fresh Polyscope Worktrees

**Changed:**

- updated `scripts/polyscope-rollout.py` so fresh Polyscope clone directories are now auto-provisioned idempotently: clone-local `polyscope.local.json` files are synced into each workspace, preview API and frontend env files are rewritten for the current workspace, generated setup commands run once per setup-hash, and successful runs leave an ignored `.polyscope-secpal-provisioned.json` marker to prevent redundant rebuilds on later syncs
- changed generated API setup from a manual preview-env rewrite plus Composer-only bootstrap to a fully automatic non-destructive preview bootstrap: `config:clear`, `migrate --force`, `db:seed --force`, and canonical `test@example.com` reconciliation now run as part of setup without relying on `migrate:fresh`, so fresh workspaces keep the standard preview login while becoming browser-auth ready without wiping the shared preview database
- restored the generated preview-facing authenticated commands to the standard `test@example.com` / `password` login instead of the temporary `test@password.com` alias, keeping fresh Polyscope workspaces and existing SecPal test habits aligned
- updated generated frontend setup so fresh workspaces also rewrite `.env.local` to the matching `api-<workspace>.preview.secpal.dev` origin before building preview assets, making the checked-out workspace itself reflect the preview target instead of only the ad-hoc build command
- fresh Polyscope clone directories now also get their local Git quality gates installed during provisioning: `pre-commit` hooks are installed when a repo ships `.pre-commit-config.yaml`, and `pre-push` is linked to `scripts/preflight.sh` when the repo exposes a preflight script, so commits and pushes from inside Polyscope clones enforce the same local checks as the primary SecPal checkouts
- extended `scripts/install-polyscope-rollout.sh` to install `polyscope-worktree-provision.service` and `polyscope-worktree-provision.path`, watching both generated repo-local `polyscope.local.json` files and Polyscope worktree metadata updates in `~/.polyscope/polyscope.db` so fresh workspace creation now triggers the automatic provisioning path instead of requiring manual setup commands afterward
- extended `tests/polyscope-rollout.sh` to cover the new non-destructive API setup command, frontend env rewrite, clone-local config syncing, ignored provision marker, idempotent reruns, and the new systemd service/path units for automatic worktree provisioning

## 2026-05-02 - Provision Preview API Domains For Fresh Polyscope Workspaces

**Changed:**

- updated `scripts/polyscope-rollout.py` so generated `api/polyscope.local.json` setup now rewrites `APP_URL`, `FRONTEND_URL`, `SESSION_DOMAIN`, `SANCTUM_STATEFUL_DOMAINS`, and `CORS_ALLOWED_ORIGINS` for the current workspace before preview provisioning continues, allowing fresh `frontend-<workspace>.preview.secpal.dev` and generic `<workspace>.preview.secpal.dev` frontends to complete browser-session auth against `api-<workspace>.preview.secpal.dev`
- extended `tests/polyscope-rollout.sh` to require the new preview API environment provisioning command in the generated API Polyscope config so fresh workspace auth does not silently regress back to the live-domain-only defaults

## 2026-05-02 - Supervise Polyscope Server Startup And Sync

**Changed:**

- updated `scripts/install-polyscope-rollout.sh` to install a real `polyscope-server.service` user unit that binds the local Polyscope API to `127.0.0.1:4321`, restarts on failure, and triggers the SecPal rollout sync after each successful server start so fresh workspace creation sees the current instructions, principles, prompts, links, and provisioning config
- kept `polyscope-rollout-sync.service` as the instruction-change sync path, but made its generated unit explicitly order after `polyscope-server.service` and pass the local API base through to the rollout script so runtime prompt/config refreshes stay aligned with the supervised server endpoint
- extended `tests/polyscope-rollout.sh` to cover the new server unit, startup refresh hook, localhost bind, rollout API base wiring, and systemd activation sequence for the supervised Polyscope runtime

## 2026-05-02 - Restore Generic Polyscope Preview Hosts

**Changed:**

- restored generic Polyscope preview URLs in generated repo-local `polyscope.local.json` files so workspaces resolve as `https://{{folder}}.preview.secpal.dev` again instead of requiring repo-prefixed hostnames
- updated the rendered preview nginx config to accept both generic and legacy repo-prefixed hosts while keeping the newer `try_files /index.html =404` fallback so missing static outputs return a clean `404` instead of an internal rewrite loop
- corrected the generated preview nginx missing-workspace fallback so it now points at a non-existent sentinel docroot and returns `404` instead of leaking into directory-index `403` responses
- updated the Polyscope rollout prompt source so repository-specific prompts and task preambles also include each repo's shared `org-shared.instructions.md` overlay instead of only the repo baseline plus one focus instruction
- changed the generated frontend Polyscope setup to build preview artifacts in `--mode preview` against the matching `https://api-${PWD##*/}.preview.secpal.dev` host, so each `frontend` workspace now talks to its linked API workspace instead of the shared `api.secpal.dev` host
- added direct frontend Polyscope run entries for local preview smoke, workspace-preview smoke, workspace-preview authenticated Playwright, and `app.secpal.dev` staging, so browser-E2E flows are available from the workspace without retyping the commands
- added an API Polyscope run that does `migrate:fresh --seed` and rewrites the seeded preview login to `test@password.com` / `password`, so the linked API workspace can be reset to a known E2E state before authenticated frontend preview runs
- documented the reserved nginx prefix routing rule (`api-`, `frontend-`, `secpal-app-`, `changelog-`) for preview hosts so future contributors know those prefixes are reserved for legacy per-repo routing

## 2026-05-02 - Restore Markdown Prettier Compliance

**Changed:**

- aligned the local pre-commit Prettier hook and this repository's code-quality workflow to the pinned repository Prettier `3.5.3`, so commit hooks, local `./scripts/preflight.sh`, and repo CI check the same formatter version instead of drifting between `pre-commit` mirror releases and npm-installed Prettier
- reformatted the pre-existing Markdown drift in `CHANGELOG.md`, `.github/CLA_SETUP.md`, `SECURITY.md`, `docs/adr/*.md`, `docs/audits/2026-03-31-adversarial-review-LOCAL-REVIEW.md`, `docs/development-principles.md`, `docs/feature-requirements.md`, `docs/ideas-backlog.md`, and `scripts/README.md` so repo-wide `./scripts/preflight.sh` no longer fails for unrelated topic branches on documentation-only Prettier issues

## 2026-05-02 - Add OpenAPI Verified-Endpoint Presence Guard

**Added:**

- `scripts/check-openapi-verified-endpoints.mjs` — regression guard that fails when `docs/openapi.yaml` omits any operation from the verified-endpoint allowlist; allowlist entries correspond to API operations with confirmed feature-test coverage in the `contracts` repo
- `tests/check-openapi-verified-endpoints.sh` — shell test that runs the guard against pass and fail fixtures, verifies exit codes and presence of the "Missing operations:" error message
- `tests/fixtures/openapi-verified-presence/pass-min.yaml` and `fail-missing.yaml` — minimal OpenAPI fixtures for test isolation
- `docs/contract-drift/US-001-evidence-matrix.md` and `docs/contract-drift/US-008-validation-and-draft-prs.md` — contract-drift evidence documentation
- `package.json` — added `test` and `test:openapi-verified-presence` scripts plus `js-yaml` devDependency so the guard runs via `npm run test` (picked up by `npm run --if-present test` in the standard preflight Node install path)

## 2026-05-01 - Document Cursor agent CLA Allowlist Exception

**Changed:**

- documented that Cursor agent-assisted commits can appear in CLA Assistant as `cursoragent` and must be allowlisted alongside `copilot-swe-agent` and the existing Dependabot bot exceptions so `cla/check` does not block bot-assisted pull requests

## 2026-05-01 - Version Polyscope Cursor Sync And Auto-Refresh

**Changed:**

- added `scripts/polyscope-rollout.py` as the versioned source of truth for SecPal Polyscope rollout state, including repo-local `polyscope.local.json` rendering, instruction-derived prompt/link sync into `~/.polyscope/polyscope.db`, and deterministic preview nginx config rendering
- added `scripts/install-polyscope-rollout.sh` so the VPS can install a stable `~/.local/bin/polyscope-secpal-rollout.py` symlink plus a systemd user `polyscope-rollout-sync.service` and `polyscope-rollout-sync.path` hook that re-syncs Polyscope whenever tracked instruction files change
- added `tests/polyscope-rollout.sh` and wired the new automation into the repository's normal shell-test/preflight path, covering local config generation, instruction-derived prompt content, repository-link sync, nginx rendering, and auto-sync unit installation
- corrected the generated `api` Polyscope setup so Laravel clones no longer run nonexistent root-level `npm install` or `npm run build` steps, fixing issue-loading failures on the VPS when Polyscope initializes API workspaces
- hardened `scripts/polyscope-rollout.py` with fail-fast validation for repo-local Polyscope commands, so future rollout drift now aborts immediately when a repo config references missing root manifests, lockfiles, npm scripts, or checked-in relative script paths
- hardened `tests/polyscope-rollout.sh` so the fake `systemctl` stub receives `SYSTEMCTL_LOG` reliably and path assertions do not depend on the clone directory containing a `/.github/scripts/` segment (local Polyscope workspaces versus GitHub Actions checkouts)
- pinned Prettier in this repository and run `tests/polyscope-rollout.sh` against `node_modules/.bin/prettier` so generated `polyscope.local.json` formatting checks do not use `npx` at test time; taught rollout validation to surface invalid `package.json` and to reject relative script paths that escape the repository root

## 2026-05-01 - Remove Stale Admin Model ADR Drift

**Changed:**

- updated the shared product and compliance docs so they no longer describe admin-labeled frontend surfaces, settings UIs, compliance-export routes, or training material after the neutral onboarding-review and Android provisioning route cleanup
- updated ADR-005, ADR-008, ADR-009 references, and activity-log examples so `.github` architecture documents no longer describe an `Admin` role, an `admin` organizational scope level, or a `super-admin` model as part of SecPal's supported authorization design after the binding cleanup decision in `SecPal/.github#404`

## 2026-04-25 - Restore Portable mktemp Test Templates

**Changed:**

- `tests/setup-project-board.sh`: replaced deprecated `mktemp -d -t ...` usage with the repository's existing full-template `${TMPDIR:-/tmp}/...XXXXXX` style
- `tests/validate-copilot-instructions.sh`: same portable `mktemp` template-path cleanup as `tests/setup-project-board.sh`
- `tests/mktemp-portability.sh`: added a focused regression test, wired into local preflight, so deprecated `mktemp -t` usage in these shell tests is caught before push
- `CHANGELOG.md`: corrected the prior 2026-04-24 wording so it no longer claims the `mktemp -t` change improved portability, because the `mktemp -d -t <template>` pattern has non-portable semantics between GNU/Linux and BSD/macOS, while the explicit full-path template `${TMPDIR:-/tmp}/...XXXXXX` works across both

---

## 2026-04-25 - Exclude Git Metadata From Local Markdownlint Preflight

**Changed:**

- `scripts/preflight.sh`: excluded `.git` from the local `markdownlint-cli2` glob set so Git ref and log metadata cannot fail Markdown validation for repository content
- `tests/preflight-markdownlint-scope.sh`: added a focused regression test, wired into local preflight, that verifies the markdownlint invocation includes the `.git` exclusion

---

## 2026-04-24 - Clarify Backlog Prerequisites And Improve Test Coverage

**Changed:**

- `docs/ideas-backlog.md`: replaced vague "affordable NLP APIs exist (GPT-4, Anthropic Claude)" with "affordable advanced NLP services are available (for example, state-of-the-art LLM APIs as of 2026)" to avoid quick-aging vendor references
- `docs/ideas-backlog.md`: expanded BWR historical implementation trail note to summarise what those issues delivered (data model groundwork, status tracking support, and compliance/reporting baseline) so readers do not need to open three separate issues for context
- `docs/ideas-backlog.md`: replaced the unclear "baseline shift-planning work is reintroduced" prerequisite with an explicit list of required functionality (manual shift assignment, schedule editing, and conflict checks)
- `docs/ideas-backlog.md`: removed the undefined "Phase 2" phase reference from the mobile notification "When to revisit" condition in favour of a concrete observable milestone
- `tests/setup-project-board.sh`: implemented actual integration test scenarios (gh unavailable, prompt-decline, prompt-accept) replacing the previous placeholder enforcement variable; the `REQUIRE_SETUP_PROJECT_BOARD_INTEGRATION_TESTED` guard now runs real tests instead of checking for an external marker variable
- `tests/validate-copilot-instructions.sh`: updated the `mktemp` call to use the `-t` flag instead of an explicit `/tmp`-prefixed template, aligning with BSD/macOS-style `mktemp` usage (with portability trade-offs on GNU systems)
- `tests/validate-copilot-instructions.sh`: replaced fragile `set +e` / `set -e` pattern in `run_validator` with a safer `if/else` exit-code capture
- `tests/validate-copilot-instructions.sh`: eliminated duplicated AI-lines literal in `wrong_license_repo` fixture by reusing the `$valid_api_extra_ai_lines` variable (DRY)

---

## 2026-04-19 - Triage Archived Feature-Requirements Planning Drift

**Changed:**

- `docs/feature-requirements.md`: added an explicit archive-triage snapshot, defined the long-term end state as a slim historical archive, and linked the few still-relevant areas to their live issue or ADR trackers instead of leaving the archive implicitly actionable
- `docs/ideas-backlog.md`: removed stale instructions that pointed contributors back to `feature-requirements.md` for active planning, replaced the BWR migration note with the existing API delivery trail, and clarified that future activation must happen through repo-local issues or epics

## 2026-04-19 - Clarify Under-1.x Compatibility Removal Guidance

**Changed:**

- `.github/copilot-instructions.md`: clarified that even this non-versioned governance repository follows the broader SecPal under-`1.x` rule, so obsolete compatibility shims should be removed instead of preserved by default when they weaken policy clarity, correctness, or security
- added a tiny tracked Apache-2.0 REUSE fixture under `tests/` so repo-wide REUSE validation and staged-file pre-commit validation agree on Apache license usage

## 2026-04-19 - Add Validator Regression Coverage For AI Triage And REUSE Edge Cases

**Changed:**

- `tests/validate-copilot-instructions.sh`: added an explicit assertion that inline SPDX headers satisfy the Copilot-instructions REUSE check without a `.license` sidecar
- `tests/validate-copilot-instructions.sh`: added a focused fixture proving repo-local negative wording like `Do not inherit from sibling repositories.` does not trigger the pseudo-inheritance validator

## 2026-04-17 - Improve Test Output Clarity and Assertion Robustness

**Changed:**

- `tests/audit-closed-epics.sh`: replaced silent `grep -q` assertions with `if ! grep -q` blocks that print the output file and a descriptive message on failure, making test failures easier to diagnose
- `tests/codeql-applicability.sh`: clarified both error messages to say "before continuing" instead of ambiguous phrasing referencing merging or enabling CodeQL
- `tests/pull-request-template.sh`: replaced the single fragile literal-string match for the changelog checklist item with a loop over key phrases using `grep -Eiq`; switched the no-overstatement check to `grep -Eq` pattern matching
- `tests/setup-project-board.sh`: added comprehensive assertions for `QUICK_REFERENCE.md` and `ROLLOUT_GUIDE.md` key phrases; added a behavioral coverage guard that requires `SETUP_PROJECT_BOARD_INTEGRATION_TESTED=1` when integration tests are absent
- `tests/validate-copilot-instructions.sh`: refactored multi-line fixture strings to use heredoc variables; aligned the `missing_api_specific` fixture to include only one of the two required API patterns; corrected the `wrong_license` sidecar fixture from `MIT` to `Apache-2.0`; switched the android fixture invocation to use the `run_validator` helper
- `docs/workflows/QUICK_REFERENCE.md`: added mentions of `optional GitHub Project Board mirror` and `status: discussion|BFD4F2|Needs decision before implementation` for consistency with the setup script
- `docs/workflows/ROLLOUT_GUIDE.md`: same consistency additions as QUICK_REFERENCE.md

## 2026-04-17 - Enforce Automatic Copilot AI Risk Validation Across Repositories

**Changed:**

- added `.github/.github/workflows/reusable-copilot-instructions.yml` so sibling repositories can run the central Copilot-instructions validator automatically from their `quality.yml` workflows
- extended `scripts/validate-copilot-instructions.sh` to distinguish Android from generic frontend repos, enforce repository-specific known-risk AI guardrails, and ignore negative "do not inherit" wording instead of treating it as pseudo-inheritance
- added a focused regression test plus local preflight enforcement for the validator so reusable-workflow and repo-specific AI-risk checks cannot silently regress
- updated the validation-system documentation to describe the new reusable workflow and automatic multi-repository enforcement path

## 2026-04-17 - Audit Closure-Ready Epic Checklist Drift

**Changed:**

- extended `scripts/audit-closed-epics.sh` so it now audits open epics too and flags stale unchecked child-issue entries when the linked work is already closed
- strengthened `tests/audit-closed-epics.sh` with a regression case for open-but-complete epics whose checklist state drifted from the actual child-issue status
- clarified `scripts/README.md` and `docs/EPIC_WORKFLOW.md` so the audit helper's broader checklist-drift coverage is documented

## 2026-04-15 - Align Project Board Helper Collateral With Issue-First Planning

**Changed:**

- updated `scripts/setup-project-board.sh` so its status-label guidance and setup messaging no longer depend on `feature-requirements.md` and instead describe the project board as an optional mirror of issue and PR state
- clarified `docs/workflows/QUICK_REFERENCE.md` and `docs/workflows/ROLLOUT_GUIDE.md` so rollout and daily board usage explicitly preserve issues, milestones, and linked PRs as the source of truth
- added a focused shell regression check for the project-board helper collateral and wired it into local preflight

## 2026-04-15 - Add AI Finding Triage Guardrails

**Changed:**

- added an explicit AI-findings triage section to the organization Copilot baseline so AI-generated fix PRs now require proof of the defect instead of relying on green CI alone
- extended `scripts/validate-copilot-instructions.sh` plus its documentation so the central validator now fails when Copilot instructions omit proof-of-defect and green-CI-is-not-enough guidance, while still accepting inline SPDX headers and repo-local "do not inherit" wording without false positives
- clarified `.github` repository conventions so shell and regex policy changes are reviewed as governance changes with explicit positive and negative evidence

## 2026-04-15 - Replace Non-Applicable CodeQL Scan With Guardrail Check

**Changed:**

- replaced the `.github` repository's stale CodeQL workflow with a lightweight applicability guardrail because the repository no longer contains any tracked CodeQL-supported JS/TS source files, which had left Code Scanning stuck on a November 2025 analysis record
- added a focused regression test plus local preflight enforcement so future changes must keep the workflow aligned with whether this repository actually contains tracked CodeQL-supported files

## 2026-04-15 - Add Changelog Accuracy PR Guardrail

**Changed:**

- added an explicit PR checklist guardrail requiring `CHANGELOG.md` edits to be checked against the actual implementation, tests, schema, or config touched by the PR and to avoid overstating behavior the code does not yet enforce
- added a focused regression test plus local preflight enforcement so the changelog-accuracy checklist item stays present in the shared pull request template

## 2026-04-15 - Adopt Issue-First Planning Governance

**Changed:**

- accepted ADR-013 to establish GitHub Issues, milestones, ADRs, and linked PRs as the canonical planning model, with the organization project board retained only as an optional mirrored view
- rewrote `docs/planning.md` as the canonical contributor planning guide and reframed `docs/project-board-integration.md` as optional board operations guidance
- archived `docs/feature-requirements.md` for active planning, clarified the non-canonical role of `docs/ideas-backlog.md`, and updated `README.md` plus `docs/workflows/PROJECT_AUTOMATION.md` to match the issue-first process
- updated the ADR index with the new planning-governance decision

## 2026-04-14 - Harden Copilot Instructions And Workflow Timeout Validations

**Changed:**

- updated SPDX copyright headers in `docs/workflows/PROJECT_AUTOMATION.md` and `docs/workflows/QUICK_REFERENCE.md` to `2025-2026`
- clarified legacy optional status messaging for `.github/copilot-config.yaml` checks in `scripts/validate-copilot-instructions.sh`
- hardened `scripts/validate-copilot-instructions.sh` against missing instruction paths, made runtime/critical-rules pattern matching more resilient, and fixed summary indentation consistency
- strengthened `tests/audit-closed-epics.sh` with explicit non-zero exit-code expectation (`1`) and a positive guard that valid checked-and-closed issues are not falsely flagged
- improved `tests/reusable-workflow-timeouts.sh` job and timeout detection to handle flexible indentation and avoid prematurely stopping scan after the first `jobs:` block

## 2026-04-11 - Fix stale doc content and remove dead files

**Changed:**

- `docs/ideas-backlog.md`: replaced the "Native Mobile Apps" future-idea stub with the current reality — Android app (`SecPal/android`, Capacitor) is in active development; iOS remains a future consideration
- `docs/development-principles.md`: replaced three stale references to `copilot-config.yaml` as "machine-readable source of truth" with correct references to `copilot-instructions.md` and per-repo `.github/instructions/*.instructions.md` files
- `docs/openapi.md`: corrected validation tool reference from Spectral CLI to Redocly CLI (`redocly lint`)

**Removed:**

- `.github/PULL_REQUEST_TEMPLATE.md`: duplicate PR template (uppercase); GitHub uses the lowercase `pull_request_template.md` — the uppercase file was inert and confusing
- `.github/copilot-config.yaml` and its `.license` sidecar: inert ~60 KB YAML from an experimental period; no Copilot mechanism reads this file; governance baseline is now fully in `copilot-instructions.md` and per-repo instruction files

## 2026-04-11 - Remove Stale Documentation

**Changed:**

- removed stale one-time artifacts and historical docs: YAML Copilot config experiment note (`docs/YAML_COPILOT_CONFIG_TEST.md`), single-fix compliance report (`docs/RETROACTIVE_COMPLIANCE_FIX_ISSUE187.md`), draft-PR-reminder bugfix note (`docs/BUGFIX_DRAFT_PR_REMINDER.md`), and implementation summaries for already-merged automation work (`IMPLEMENTATION_SUMMARY.md`, `WORKFLOW_REVIEW.md`)

## 2026-04-11 - Add Closed Epic Audit Helper

**Changed:**

- added `scripts/audit-closed-epics.sh` to audit closed Epic issues for stale checklist state, unresolved child issues, and false positives caused by PR references in issue bodies
- added a focused shell regression test and wired it into local preflight so future changes keep the audit helper correctly distinguishing issue links from PR links
- documented the retrospective audit command in the shared Epic workflow guide and scripts reference so maintainers can re-check closed epics before trusting their closure state

## 2026-04-11 - Add Timeouts To Inline Workflow Jobs

**Changed:**

- added explicit `timeout-minutes` values to the remaining inline `.github` workflow jobs so organization automation no longer falls back to GitHub Actions' six-hour default for actionlint, draft PR reminders, license checks, project automation, quality checks, REUSE, and the inline workflow test harness job

## 2026-04-11 - Add OFL-1.1 To License Compatibility Allowlist

**Changed:**

- added OFL-1.1 (SIL Open Font License 1.1) to the compatible licenses list in both the
  reusable and standalone license-compatibility workflows; for font-embedding scenarios this
  was assessed as generally compatible with AGPL-3.0-or-later, but outcomes are context-specific
  and should be confirmed against authoritative guidance and legal review

## 2026-04-11 - Add Job Timeouts To Reusable Workflows

**Changed:**

- added explicit `timeout-minutes` values to every previously unbounded job in the reusable GitHub Actions workflows so caller repositories inherit bounded execution instead of GitHub's six-hour default
- added a focused `tests/reusable-workflow-timeouts.sh` regression check and wired it into local preflight so missing reusable workflow timeouts fail before push

## 2026-04-11 - Add changelog Repository To Workspace Inventory

**Changed:**

- added the new `changelog` repository to the shared workspace inventory and contributor setup documentation so contributors know to clone and configure it alongside the other active SecPal repositories
- extended the master `.github/setup-hooks.sh` bootstrap and its regression test to install hooks in `changelog` together with the existing repositories
- refreshed organization workspace documentation and repository listings so contributor setup guidance reflects the current seven-repository SecPal workspace

## 2026-04-11 - Centralize Epic Closure Evidence And CLA Ops Verification

**Changed:**

- added a central `docs/EPIC_WORKFLOW.md` guide in the `.github` repository so epic and sub-issue governance no longer depends on the `api` repository as the documentation source of truth
- strengthened the organization issue templates, markdown Copilot baseline, and machine-readable Copilot config to require explicit parent-epic closure evidence, repo-by-repo acceptance verification, and pre-closure tracking of reopened or deferred follow-up work
- extended CLA setup guidance and maintainer-facing docs to require live verification of the external CLA Assistant allowlist and `cla/check` behavior for automated authors such as `copilot-swe-agent`, reducing the chance of future bot PR blockage being treated as fixed based on documentation alone

## 2026-04-08 - Fix setup-hooks Success Counter Abort

**Fixed:**

- replaced the `((SUCCESS_COUNT++))` arithmetic post-increments in `setup-hooks.sh` with `set -e` safe assignment increments so the workspace hook bootstrap no longer aborts after the first successful repository
- added a focused shell regression test that exercises the happy-path multi-repository bootstrap and verifies the final success summary is reported

## 2026-04-06 - Adopt apk.secpal.app Android Distribution Governance

**Changed:**

- accepted `apk.secpal.app` as the canonical Android artifact and download host in the organization-wide domain policy, machine-readable Copilot governance, and local domain validation script
- documented the split between the technical Android artifact host and the human-facing Android landing surface at `secpal.app/android`
- recorded the single-package Android distribution strategy and the rule that provisioning QR codes must be generated privately inside SecPal with short-lived bootstrap tokens rather than published as public static artifacts

## 2026-04-06 - Strengthen Validation Governance

**Changed:**

- strengthened Required Validation to require same-commit test or validation updates when a fix alters observable behavior, validation rules, or automation logic
- mandated `--body-file` for programmatic PR creation in Issue And PR Discipline to prevent shell escaping issues

## 2026-04-06 - Document Copilot CLA Allowlist Exception

**Changed:**

- documented that Copilot-created pull requests currently use the author account `copilot-swe-agent` and must be allowlisted in CLA Assistant alongside the existing Dependabot bot exceptions so the organization-wide `cla/check` status does not block automated PRs

## 2026-04-04 - Clarify Clean Main Start And Post-Merge Readiness

**Changed:**

- clarified that every new work branch must start from a clean, up-to-date local `main`, including an explicit fast-forward pull before the topic branch is created
- extended the documented post-merge cleanup sequence to cover returning to `main`, pulling with fast-forward only, pruning and deleting merged branches, refreshing Composer or Node dependencies where applicable, and confirming the repository is clean again afterward

## 2026-04-04 - Restore Strict Copilot Governance Clarity

**Changed:**

- restored explicit always-on Copilot governance in the central `.github/copilot-instructions.md`, reinstating unambiguous TDD-first, quality-first, one-topic-per-PR, immediate issue-creation, and EPIC-plus-sub-issue rules after the earlier context-bloat reduction made them too implicit at runtime
- tightened `.github/copilot-config.yaml` validation with explicit KISS, YAGNI, one-topic, issue-management, and quality-first emphasis so the central source of truth is stricter than before the rollback
- clarified the PR lifecycle so finished work must be self-reviewed, committed, and pushed before any PR exists, and the first PR state must always be draft until the final PR-view self-review is clean

## 2026-04-03 - Document Local actionlint Remediation For Preflight Warnings

**Changed:**

- made the local `scripts/preflight.sh` warning for missing `actionlint` explicitly point maintainers to `pre-commit run actionlint --all-files` and an optional standalone install path via `go install github.com/rhysd/actionlint/cmd/actionlint@latest`
- extended `setup-hooks.sh`, `WORKSPACE_SETUP.md`, and system-requirements guidance so workspace bootstrap now explains that workflow linting already works through pre-commit hooks and CI even when the standalone `actionlint` binary is absent

## 2026-04-03 - Rename Android Identifier To app.secpal

**Changed:**

- updated the organization-wide Android identifier baseline to `app.secpal`, removed the old identifier exception from current governance text and Copilot configuration, and tightened the shared domain-check allowlist so legacy former host-style strings are no longer implicitly accepted

## 2026-04-01 - Fix Cross-Repo Composite Action Resolution In Reusable Workflows

**Fixed:**

- inlined the Node.js setup and dependency-install steps back into `reusable-prettier.yml` and `reusable-openapi-lint.yml` to restore cross-repo compatibility; GitHub Actions cannot resolve composite actions stored under `.github/actions/` in an external repository when referenced from a step inside a reusable `workflow_call` workflow, causing all callers (`frontend`, `secpal.app`) to fail with "Can't find action.yml"
- the composite action `setup-node-with-deps` is retained for potential future use once a supported path layout is confirmed

## 2026-04-01 - Refactor Reusable Node Workflow Setup

**Changed:**

- extracted the duplicated Node setup and dependency-install logic from the reusable Prettier and OpenAPI lint workflows into a shared composite action
- added explicit lockfile handling for those reusable workflows so missing `package-lock.json` now warns and falls back to `npm install` by default, with an opt-in `require-lockfile` mode for stricter callers
- aligned the touched reusable workflows with current governance expectations by adding explicit `contents: read` permissions and job timeouts

## 2026-04-01 - Tighten Local Tooling Guidance And Workspace Hook Coverage

**Changed:**

- clarified that local `scripts/preflight.sh` does not invoke `actionlint` directly, while workflow linting remains enforced through pre-commit hooks and CI, and documented the optional manual local `actionlint` path consistently across contributor docs
- extended the master `setup-hooks.sh` workspace bootstrap to include the active `android` and `secpal.app` repositories and refreshed the workspace setup guide to match the current six-repository layout

## 2026-04-01 - Adversarial Security Review Second Pass

**Added:**

- completed second-pass adversarial security audit targeting subtle, non-obvious vulnerabilities overlooked in standard reviews
- identified 14 substantive findings (3 critical, 5 high, 6 medium severity) including Merkle tree cryptography weakness, race conditions, and contract/implementation misalignment
- documented findings in `docs/audits/2026-03-31-adversarial-review.md` with exact code references and remediation guidance

## 2026-04-01 - Reduce Copilot Instruction Context Bloat

**Changed:**

- replaced the oversized organization-level Copilot runtime instructions with a shorter self-contained baseline and removed dead `copilot-config.yaml` references that no longer resolve in this repository
- tightened the guidance to the rules that actually need to stay always-on so multi-repo VS Code workspaces send less redundant governance text with each Copilot request
- updated `validate-copilot-instructions.sh` runtime-model checks to accept the new condensed phrasing alongside the original wording

## 2026-03-29 - Align Cross-Repo Domain Policy With Active .dev Hosts

**Changed:**

- corrected the organization-wide domain policy text so `secpal.app` is limited to the public homepage and real email addresses, while `api.secpal.dev` and `app.secpal.dev` are the active API/PWA hosts and the Android application identifier remains Android-only
- updated the shared `check-domains.sh` guidance to flag deprecated `.app` web-host usage separately from valid Android identifier references
- refreshed historical ADR and feature-requirement examples that still used legacy `.app`-style SecPal subdomains as active tenant or employee web-host examples

## 2026-03-22 - Refresh Governance Baseline Docs For Live Repository State

**Changed:**

- Added the `github-actions` automation label to the organization label standard and label sync script
- Updated the GHAS baseline guide to document the live required defaults for `allow_auto_merge`, secret scanning, push protection, Dependabot security updates, and the Copilot review ruleset
- Replaced stale "planned repository" language in the GHAS guide with the current repository classes and added repeatable audit commands for checking live repository settings

**Why:**

The cross-repository governance drift report in Issue #254 was partly based on an older snapshot. The `.github` source documents should describe the current baseline clearly enough that future audits and label sync runs measure the intended state instead of outdated assumptions.

**Impact:**

- Label sync now includes the `github-actions` label expected by Dependabot configurations
- Security baseline guidance now matches the live SecPal repository fleet instead of October 2025 rollout assumptions
- Future governance audits can verify current settings with documented CLI commands instead of relying on stale issue text

## 2026-03-22 - Remove Stale DDEV Assumptions From Governance Docs

**Changed:**

- Replaced DDEV-specific API coverage commands in `CONTRIBUTING.md` with direct `php artisan test` examples
- Updated the system requirements guide and helper script to describe the API runtime as native PHP, remove DDEV as a requirement, and add SSH-friendly guidance for remote execution

**Why:**

Issue #255 correctly identified that organization-level docs and helper scripts were still steering contributors toward a DDEV workflow that no longer matches the active API runtime.

**Impact:**

- Contributors and agents now see API setup guidance that matches the direct shell and SSH-based workflow used by the current Laravel runtime
- The system requirements script no longer reports DDEV as a mandatory API dependency
- Coverage and troubleshooting examples no longer suggest DDEV-only commands

## 2026-03-22 - Enforce Branch Hygiene Before Local Work Starts

**Changed:**

- Added an explicit pre-work branch hygiene workflow to the organization-level Copilot YAML and markdown instructions
- Defined that AI must inspect `git status --short --branch` before edits, never start implementation on local `main`, and stop when an existing non-`main` branch already contains unrelated uncommitted changes
- Added explicit SPDX year-maintenance guidance so edited files and license sidecars keep `SPDX-FileCopyrightText` at the current calendar year using `YYYY` or `YYYY-YYYY` without spaces as appropriate
- Clarified that files without inline SPDX headers must use their companion `.license` files for the same year-maintenance rule
- Added explicit warning-triage guidance so non-fatal diagnostics, audit findings, and deprecation notices must be reviewed and either fixed or tracked immediately

**Why:**

Branch protection on `main` only helps at merge and push time. It does not prevent local mixed work if an agent starts editing on `main` first and creates a topic branch only after hitting protection.

**Impact:**

- Agents now have a documented start-of-work rule instead of relying on branch protection alone
- Dirty non-`main` branches must be assessed before new work continues, which reduces accidental mixed commits across topics
- Edited governance files are less likely to keep stale copyright years after routine maintenance
- Non-fatal tool warnings are less likely to be ignored just because a script still exits successfully

## 2026-03-20 - Replace DDEV Runtime Assumptions In Copilot Guidance

**Changed:**

- Updated organization-level Copilot instructions and YAML guidance to describe the API backend as a native PHP runtime instead of a DDEV-only environment
- Replaced DDEV-specific command examples in the machine-readable backend guidance with direct shell, SSH, and log access guidance that fits the current VPS workflow

**Why:**

SecPal API development now runs directly on the VPS in a full server environment. Organization guidance should not keep telling agents to use container wrappers that are no longer part of the active workflow.

**Impact:**

- Cross-repo AI guidance now matches the real backend runtime and command surface
- Agents are less likely to suggest `ddev exec`, `ddev ssh`, or DDEV-only tooling when operating on the API repository remotely

## 2026-03-19 - Align Laravel Version References With Current Runtime

**Changed:**

- Updated organization-level backend stack references from Laravel 12 to Laravel 13 in the active Copilot guidance and changelog narrative
- Updated `copilot-config.yaml:stack.backend.framework_version` from `12.x` to `13.x` (YAML Single Source of Truth)
- Updated Laravel authorization doc link in `docs/adr/20251108-rbac-spatie-temporal-extension.md` from `12.x` to `13.x`

**Why:**

The API runtime has already been upgraded to Laravel 13, so organization and repository guidance should not continue advertising the old framework baseline.

**Impact:**

- Cross-repo guidance now matches the current Laravel baseline
- `copilot-config.yaml` (machine-readable YAML, primary source for AI tooling) now consistently reflects Laravel 13
- Future repo maintenance is less likely to reintroduce stale Laravel 12 wording into active documentation

## 2026-03-15 - Refresh Stale Product Examples In Development Principles

**Changed:**

- Replaced deleted feature-specific controller, component, hook, and fail-fast examples in `docs/development-principles.md` with current customer-oriented examples

**Why:**

The organization guidance should not teach patterns using a product feature that has already been removed from the active SecPal repositories.

**Impact:**

- Documentation examples now match the current product direction
- New contributors are less likely to reintroduce deleted feature vocabulary into fresh code

## 2026-03-08 - Automate Copilot Review Memory

**Added:**

- **`scripts/copilot-review-tool.sh`** - CLI automation for the Copilot review workflow
  - Fetches Copilot review threads from a PR via GraphQL
  - Exports thread reports in Markdown or JSON
  - Generates durable lessons artifacts that can outlive a single chat session
  - Scans open non-draft PRs across multiple SecPal repositories in one run
  - Aggregates machine-readable finding exports into recurring categories and syncs durable tracking issues
  - Resolves review threads via GraphQL without using comment replies
  - Validates CLI arguments, supports `--max-prs`, and warns when GitHub pagination truncates exports
- **`docs/copilot-review-automation.md`** - operational guide for using review artifacts as durable memory and promoting repeated findings into instructions, hooks, lint rules, tests, and CI
- **`.github/workflows/copilot-review-memory.yml`** - scheduled artifact export for unresolved Copilot findings across `api`, `frontend`, `contracts`, and `.github`
- **`package.json` scripts** for `copilot:review:threads`, `copilot:review:lessons`, `copilot:review:scan`, `copilot:review:resolve`, and `copilot:review:track`
- Persistent category-tracking issues in `SecPal/.github` once recurring findings cross the configured threshold
- Scheduled organization-level workflow runs that export unresolved Copilot findings as workflow artifacts
- Package metadata and lockfile names were aligned for consistent `npm` behavior

**Why:**

Private agent memory cannot be written safely from repository automation.
The maintainable alternative is to automate the durable parts of the process:
capture review findings, turn them into persistent lessons, and promote repeated issues into deterministic guardrails.

**Impact:**

- Copilot review handling no longer depends on manual GraphQL one-offs
- Lessons learned can be persisted as repo-owned artifacts instead of vanishing with a session
- Repeated Copilot findings can be converted into enforceable rules faster
- Recurring review categories now survive PR closure through durable tracking issues
- Open PRs can be scanned automatically on a schedule instead of relying on manual execution
- Scheduled runs generate less artifact noise while still keeping review exports available when findings exist

## 2026-03-08 - Fix Copilot Instruction Validator For Runtime Model

**Fixed:**

- **`scripts/validate-copilot-instructions.sh`** now validates the current self-contained runtime model instead of obsolete `@EXTENDS` and org-reminder assumptions
- Added checks for runtime-model wording, active-instruction frontmatter, and pseudo-inheritance marker removal

**Why:**

The validator still enforced the old pseudo-inheritance approach even though the active repositories now rely on repo-local, self-contained instruction files.

**Impact:**

- Local and CI validation now match the actual Copilot instruction architecture
- False positives from outdated `@EXTENDS` and org-reminder checks are removed

## 2026-03-08 - Harden Copilot Instructions for Multi-Repo Workspace

**Changed:**

- **Clarified** `.github/copilot-instructions.md` runtime semantics — this file is authoritative only inside the `.github` repository itself and does not automatically inherit into sibling repos.
- **Scoped** `.github/instructions/github-workflows.instructions.md` to GitHub automation files only with `applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml,.github/dependabot.yml,.github/dependabot.yaml"`.
- **Aligned companion repo layouts** in `api/`, `frontend/`, and `contracts/` to use self-contained `.github/copilot-instructions.md` files plus targeted `.github/instructions/*.instructions.md` overlays.

**Why:**

VS Code Copilot only loads `.instructions.md` files from the **active workspace root**.
Since `SecPal/.github` is a separate git repo opened as its own workspace folder, sibling
repository rules are not inherited at runtime. Self-contained repo-local instruction files
are the reliable way to keep organization principles and repository-specific guidance active.

**Impact:**

- No more reliance on comment-based pseudo-inheritance across repositories
- Repo-local instruction baselines are explicit and predictable in `api/`, `frontend/`, and `contracts/`
- Workflow rules now activate only for workflow and Dependabot files instead of all YAML files

---

## 2025-11-23 - Fix Dependabot Auto-Merge Job Timeout

**Fixed:**

- **Job timeout issue:** Added `timeout-minutes: 20` to the `auto-merge` job in `reusable-dependabot-auto-merge.yml` to prevent workflows from hanging indefinitely
  - Workflows were waiting unboundedly even when all CI checks had already completed
  - Job now fails after 20 minutes instead of running indefinitely
  - Works in conjunction with existing `continue-on-error: true` on the wait step (added 2025-11-14)
  - Resolves hanging workflows in SecPal/api#238 and SecPal/api#239

**Impact:**

- Dependabot auto-merge workflows complete within reasonable timeframe
- Failed workflows provide clear timeout signal instead of appearing stuck
- Aligns with GitHub Actions best practices for job-level timeout enforcement

---

## 2025-11-23 - Design Principles Consolidation (DRY Compliance)

**Added:**

- **`docs/development-principles.md`** - Human-readable guide for all development principles
  - Comprehensive documentation with code examples (TypeScript + Laravel)
  - Covers all 16 principles: 5 Essential Development Principles (Quality First, TDD, DRY, Clean Before Quick, Self Review Before Push), 5 SOLID Principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion), 3 Additional Design Principles (KISS, YAGNI, Separation of Concerns), and 3 Security & Best Practices (Fail Fast, Security by Design, Convention over Configuration)
  - Clearly marked as human-readable version with reference to YAML as source of truth
  - Framework-specific guidelines for Laravel and React/TypeScript
  - Practical application checklists

**Changed:**

- **`.github/copilot-config.yaml`** - Extended AI source of truth with additional principles

  - Added `kiss`: Keep It Simple, Stupid principle
  - Added `yagni`: You Aren't Gonna Need It principle
  - Added `separation_of_concerns`: Controller → Service → Repository pattern
  - Added `fail_fast`: Early error detection and validation
  - Added `security_by_design`: Input validation, no sensitive logging, multi-layer auth
  - Added `convention_over_configuration`: Framework conventions (Laravel, React)
  - All principles with rules, validation, and examples

- **`.github/copilot-instructions.md`** - Updated AI instructions with all principles
  - Added KISS, YAGNI, Separation of Concerns, Fail Fast, Security by Design to Core Principles section
  - Updated Pre-Commit Checklist to include all 16 principles
  - Added reference to `copilot-config.yaml:development_principles` for complete details

**Related Changes:**

- For API repository documentation updates, see SecPal/api#214

**Impact:**

- ✅ **DRY Compliance**: Single source of truth for all development principles
- ✅ **AI Optimized**: YAML for fast parsing, instructions referencing all principles
- ✅ **Human Readable**: Comprehensive markdown guide with examples
- ✅ **Multi-Repo Ready**: Central documentation, repos reference it (no duplication)
- ✅ **Complete Coverage**: All 16 principles documented for both AI and humans
- ✅ **Consistency**: All repos follow same principles via central documentation

**Structure:**

```text
.github/
├── .github/copilot-config.yaml          # 🤖 AI Source of Truth
├── .github/copilot-instructions.md      # 🤖 AI Instructions (updated)
└── docs/development-principles.md       # 👨‍💻 Human Guide (NEW)

api/
├── DEVELOPMENT.md                       # Quick Ref + Link to .github
└── docs/COPILOT_REMINDER_PATTERNS.md    # Links to .github
```

**Related:**

- Addresses #ISSUE (if any)
- Part of ongoing effort to maintain DRY compliance across multi-repo structure
- Complements existing copilot-config.yaml SOLID principles documentation

---

## 2025-11-21 - Fix Codecov Blocking Dependabot PRs

**Fixed:**

- **Codecov blocking Dependabot auto-merge** - Dependabot PRs in `api` and `frontend` were failing codecov checks despite all GitHub Actions passing
  - Root cause: `require_ci_to_pass: true` caused Codecov to wait for CI before reporting status
  - Dependabot PRs use `continue-on-error: true` for codecov upload (security best practice - no token access)
  - Codecov interpreted skipped upload as failed check and blocked PRs
  - Affected PRs: SecPal/api#204, SecPal/frontend#181, SecPal/frontend#182, SecPal/frontend#183, SecPal/frontend#184, SecPal/frontend#185

**Changed:**

- **`.codecov.yml` configuration** - Adjusted to allow Dependabot PRs while maintaining coverage enforcement

  - Set `require_ci_to_pass: false` - Codecov won't wait for CI checks before reporting
  - Set `wait_for_ci: false` - Don't wait for all CI to complete
  - Kept `informational: false` - Coverage remains **REQUIRED** for normal developer PRs
  - Kept `if_ci_failed: error` - Accurate coverage failure reporting

- **Branch Protection Rules** - Removed `codecov/patch` from required status checks via GitHub API
  - Applied to `SecPal/api` and `SecPal/frontend` repositories
  - Codecov still runs and reports, but doesn't block PRs when no data is uploaded
  - ✅ Applied manually via `gh api` commands (script provided as reference: `scripts/configure-codecov-optional.sh`)

**Impact:**

- ✅ Dependabot PRs can auto-merge: No codecov upload (continue-on-error) + codecov not required = no blocking
- ✅ Coverage enforcement **MAINTAINED**: Normal PRs still require 80% coverage (informational: false)
- ✅ Developer PRs with <80% coverage will **FAIL** codecov check (as intended)
- ✅ No security compromise: Continues using `continue-on-error` for Dependabot uploads
- ✅ **Automated solution:** Branch protection updated via GitHub API - no manual steps needed

**Technical Details:**

The key insight: `require_ci_to_pass: false` allows Dependabot PRs to proceed when no coverage data is uploaded.

- Normal PRs: Upload succeeds → Coverage calculated → Must meet 80% threshold (informational: false)
- Dependabot PRs: Upload skipped (continue-on-error) → No coverage data → Codecov doesn't block (require_ci_to_pass: false)
- Result: Coverage enforcement for developers, no blocking for Dependabot

**Related Issues:**

- This PR fixes the blocking issue for the following Dependabot PRs:
- SecPal/api#204 (actions/checkout 5→6)
- SecPal/frontend#181 (actions/checkout 5→6)
- SecPal/frontend#182 (vite 7.2.2→7.2.4)
- SecPal/frontend#183 (@vitest/coverage-v8 4.0.10→4.0.12)
- SecPal/frontend#184 (@vitest/ui 4.0.10→4.0.12)
- SecPal/frontend#185 (vitest 4.0.10→4.0.12)

**Note:** This PR does NOT close the above issues. They will auto-merge once this configuration is deployed.

---

## 2025-11-16 - Issue Management Protocol (Critical Rule #6)

**Added:**

- **Critical Rule #6: Issue Management Protocol** - ZERO TOLERANCE enforcement for immediate issue creation

  - MANDATORY: Create GitHub issue immediately when bug/issue found in old code that cannot be fixed now
  - MANDATORY: EPIC + sub-issues structure for ALL features requiring >1 PR (>600 lines, multi-module, >1 day work)
  - Top-level `issue_management` section in `copilot-config.yaml` (200+ lines) with complete protocol, workflows, examples
  - Pre-commit checklist item: "Issue Creation Protocol" validates all findings documented as GitHub issues
  - AI Execution Protocol updated with prominent reminder: "Found bug → CREATE GITHUB ISSUE NOW"
  - Forbidden patterns: "TODO: fix later" without issue reference, "we should fix X" without creating issue
  - Cross-reference to `api/docs/EPIC_WORKFLOW.md` for detailed EPIC/sub-issue guidance (superseded by `docs/EPIC_WORKFLOW.md` in this repository)

- **Issue Management section in Markdown** - Clear, concise rules added before Critical Rules section
  - Immediate issue creation protocol: 8 scenarios requiring immediate action (bugs, tech debt, coverage gaps, etc.)
  - **Security exception:** Vulnerabilities use SECURITY.md for responsible disclosure, NOT public issues
  - EPIC structure requirements: When to use (4 criteria), how to structure (epic → sub-issues → PRs), PR linking rules
  - GitHub CLI commands for issue/epic/sub-issue creation
  - Real-world example: Issue #50 with 7 sub-issues demonstrating complete workflow

**Changed:**

- **Streamlined `review_automation` section** - Replaced 70-line `issue_management` subsection with concise cross-reference

  - Maintains DRY principle: Single authoritative source for issue management rules
  - Old section duplicated information now in top-level `issue_management` section
  - Reduced review_automation from 180 lines to ~115 lines

- **Pre-Commit Checklist enhanced** - Added "Issue Creation Protocol" item (4 validation points)

  - "All discovered bugs/improvements have GitHub issues?"
  - "No 'TODO: fix later' comments without issue reference?"
  - "Complex features (>1 PR) have EPIC + sub-issues structure?"
  - "All unrelated findings documented as separate issues?"

- **AI Execution Protocol** - Added critical reminder at top: Issue creation now equal priority to TDD and Quality Gates
- **PR Rules section** - Updated unrelated findings guidance: "CREATE GITHUB ISSUE IMMEDIATELY (Critical Rule #6)"

**Documentation:**

- All issue management rules consolidated in single location (`copilot-config.yaml:issue_management`)
- Complete AI workflows: Discovery workflow (assess → create issue) and Feature planning workflow (assess complexity → EPIC or simple issue)
- Examples: Security bug during docs work, test coverage gap during feature implementation, duplication refactoring
- EPIC workflow: 6-step process from epic creation to final PR closing epic
- Cross-references: `api/docs/EPIC_WORKFLOW.md` for detailed guide with Issue #50 real-world example (superseded by `docs/EPIC_WORKFLOW.md` in this repository)

---

## 2025-11-16 - Core Development Principles Enhancement

**Added:**

- **SOLID Principles:** Added comprehensive SOLID principles to core development guidelines

  - Single Responsibility Principle (SRP): One class/function = one reason to change
  - Open/Closed Principle (OCP): Open for extension, closed for modification
  - Liskov Substitution Principle (LSP): Subtypes must be substitutable for base types
  - Interface Segregation Principle (ISP): Many small interfaces > one large interface
  - Dependency Inversion Principle (DIP): Depend on abstractions, not concretions
  - Documentation added to both `.github/copilot-instructions.md` and `.github/copilot-config.yaml`

- **English-Only Communication Rule:** Clarified language policy for GitHub communication

  - All issues, PRs, comments, and documentation MUST be in English
  - Ensures accessibility for international contributors
  - Exceptions: German legal documents (CLA, licenses) and user-facing i18n translations
  - Added to Pre-Commit Checklist for validation

- **No Literal Quotes Rule:** Added guideline against verbatim code duplication
  - Never copy/paste large code blocks without understanding
  - Reference code by file path and line numbers instead
  - Reduces maintenance burden and prevents confusion
  - Correct approach: "See `src/utils/auth.ts` lines 45-60" vs copying 50 lines

**Changed:**

- **Pre-Commit Checklist (Markdown & YAML):** Updated with new validation items

  - Added SOLID Principles check to both markdown documentation and YAML source of truth
  - Added English Only communication check to both markdown and YAML
  - Added No Literal Quotes check to both markdown and YAML
  - DRY Principle already present, now part of comprehensive development principles
  - YAML `copilot-config.yaml:checklists.pre_commit` is the authoritative source

- **Core Development Principles:** Restructured and expanded

  - DRY (Don't Repeat Yourself) now part of formal development principles
  - Quality Over Speed explicitly documented (removed from Critical Rules to avoid duplication)
  - All principles with validation guidance and examples

- **Critical Rules:** Simplified to avoid duplication
  - Removed "Quality Over Speed" from Critical Rule #6 (now only in Core Development Principles)
  - Renumbered subsequent rules (CHANGELOG Mandatory is now #6 instead of #7)

**Impact:**

- Improved code quality through explicit SOLID adherence
- Better international collaboration with English-only policy
- Reduced code duplication in documentation and comments
- Clearer expectations for all contributors

**Files Modified:**

- `.github/copilot-instructions.md` - Added Core Development Principles section before Critical Rules
- `.github/copilot-config.yaml` - Added `development_principles` section with detailed SOLID, DRY, quality-first, communication, and no-literal-quotes rules

**Related:**

- Addresses maintainer request for explicit SOLID principles documentation
- Complements existing DRY principle from Pre-Commit Checklist
- Aligns with Quality-First philosophy from core rules

---

## 2025-11-15 - Reusable Workflow for Conflict Marker Detection

**Added:**

- **Reusable workflow:** Created `reusable-check-conflict-markers.yml` for organization-wide conflict marker detection
  - Downloads and executes shared `scripts/check-conflict-markers.sh`
  - Supports customizable checkout ref via input parameter
  - Detects Git conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`, `|||||||`
  - Prevents accidental commits of unresolved merge conflicts

**Changed:**

- **Migrated `.github` repository:** Updated local `check-conflict-markers.yml` to use reusable workflow
  - Eliminates code duplication (DRY principle)
  - Single source of truth for conflict detection logic
  - Simplifies maintenance across all repositories

**Impact:**

- All SecPal repositories can now use the shared workflow
- Future improvements benefit all repos automatically
- Consistent conflict detection across the organization

**Migration Path:**

Other repositories (api, frontend, contracts) can migrate by updating their workflows:

```yaml
jobs:
  conflict-markers:
    uses: SecPal/.github/.github/workflows/reusable-check-conflict-markers.yml@main
```

**Related:**

- Resolves #176: feat: add merge conflict marker check to shared CI/preflight workflow
- Original implementation: SecPal/frontend#113
- Original issue: SecPal/frontend#96

---

## 2025-11-15 - Code Coverage Integration with Codecov

**Added:**

- **Organization-wide Codecov configuration:** Created `.codecov.yml` with coverage thresholds and policies
  - Global coverage target: 80% for project and patches
  - Precision: 2 decimal places, round down
  - Coverage range: 70-100%
  - Backend flag (`api/`) and Frontend flag (`frontend/`)
  - Comprehensive ignore patterns for tests, configs, build artifacts
  - PR comments enabled with coverage diff and tree view
  - Strict CI enforcement: `if_ci_failed: error`

**Changed:**

- **Documentation updates:**
  - Added Code Coverage section to `CONTRIBUTING.md` with local commands and requirements
  - Updated `copilot-instructions.md` with coverage enforcement rule (#11)
  - Added Codecov badges for backend and frontend to organization README
  - Minimum 80% coverage for new code, 100% for critical paths documented

**Implementation:**

- Part of Epic #189: Implement Code Coverage Tracking with Codecov
- Sub-Issue #190: Organization-Level Codecov Configuration & Documentation
- Enables coverage tracking across `api` and `frontend` repositories
- Coverage visible in Codecov dashboard and PR comments

**Impact:**

- Quality gate completion: Coverage requirements now enforced automatically
- Developers can view coverage locally and in CI
- Branch protection can enforce coverage thresholds (to be configured)

---

## 2025-11-15 - Fix Draft PR Reminder Firing on ready_for_review Event

**Fixed:**

- **Draft PR reminder false trigger:** Modified `draft-pr-reminder.yml` to prevent reminder comments when converting draft PR to "Ready for review"
  - Added explicit action check: `github.event.action == 'opened'` to job condition
  - Previously fired on both `opened` and `ready_for_review` events due to reusable workflow behavior
  - Now only reminds on NEW non-draft PRs, not when draft is converted to ready (intended workflow)
  - Resolves confusing duplicate comments on PRs that correctly started as drafts (e.g., api#158)

**Technical Details:**

- Reusable workflows (`workflow_call`) ignore their own `on:` section and inherit all events from calling workflow
- Calling workflows (`project-automation.yml`) trigger on multiple events: `opened`, `ready_for_review`, `closed`, `converted_to_draft`
- Job condition now checks both draft status AND action type to distinguish between new PR and status changes

**Impact:**

- No more false reminders when following correct draft → ready workflow
- Fix automatically applies to all repositories (api, frontend, contracts) using the reusable workflow
- DRY compliance maintained - single centralized fix

**Documentation:** `docs/BUGFIX_DRAFT_PR_REMINDER.md` (removed — historical reference only)

---

## 2025-11-14 - Fix Dependabot Auto-Merge Timeouts

**Fixed:**

- **Workflow timeout issue:** Modified `lewagon/wait-on-check-action` step in `reusable-dependabot-auto-merge.yml` to add `allowed-conclusions: success,skipped,neutral` and `continue-on-error: true`, allowing the workflow to proceed even when checks like `license/cla` are skipped or neutral
  - Step previously waited for ALL branch protection checks to reach "success" conclusion, causing 50+ minute timeouts
  - `license/cla` check is marked as required by branch protection but comes from external app and may return "neutral" or be skipped for Dependabot PRs
  - GitHub's native auto-merge (`gh pr merge --auto`) already waits for required checks automatically
  - Resolves timeout issues blocking Dependabot PRs across multiple repositories (frontend#131, #126, #127, #128, #129)

**Impact:**

- Auto-merge workflows now complete successfully instead of timing out after 50+ minutes
- Dependabot PRs can merge automatically as designed across all SecPal repositories

**Related:** PR #184

---

## 2025-11-14 - Fix CodeQL Workflow for Repositories Without JavaScript/TypeScript

**Fixed:**

- **CodeQL false failure:** Modified `codeql.yml` workflow to check for JavaScript/TypeScript file presence before running analysis
  - Added `check-languages` job that scans for `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs` files (excluding `node_modules` and `.git`)
  - `analyze` job now only runs when `has-javascript=true`, preventing failures in repositories without JS/TS code
  - Resolves CodeQL failure in `.github` repository which contains only YAML/Markdown/Shell files

**Impact:**

- CodeQL workflow succeeds with skipped analysis for repositories without JavaScript/TypeScript code
- Branch protection checks pass for non-JS/TS repositories (e.g., `.github` org defaults repo)
- No false negatives - repositories with JS/TS code still get full security analysis

**Technical Details:**

- Uses `find` command with file extensions and path exclusions for reliable detection
- Conditional job execution via `needs` and `if` ensures proper GitHub Actions check reporting
- Compatible with branch protection rules expecting "CodeQL" check status

**Related:** Discovered during PR #184 review

---

## 2025-11-11 - ADR-005: RBAC Design Decisions

**Added:**

- **ADR-005:** `docs/adr/20251111-rbac-design-decisions.md` - Formal documentation of three critical RBAC design decisions:
  - **Decision 1:** No System Roles - All roles are equal with unified deletion rules and idempotent seeder recovery
  - **Decision 2:** Direct Permissions - Users can have permissions independent of roles for exceptional access cases
  - **Decision 3:** Temporal Assignments Optional - Permanent by default, temporal only when explicitly needed
- **Updated:** `docs/adr/README.md` - Added ADR-005 and ADR-004 to "Accepted" section, created proper section structure

**Context:**

- These decisions emerged during RBAC Phase 4 planning (Issue SecPal/api#108) and were previously only documented in issue threads
- Formalizing as ADR ensures architectural decisions are permanently recorded and linked for future reference
- Supports Phase 4 implementation where other documentation (#143-145) must reference these decisions

**Related:** Issue SecPal/api#142

---

## 2025-11-09 - System Requirements Check Script

**Added comprehensive system validation script for multi-repo setup:**

- **New script:** `scripts/check-system-requirements.sh` - Validates all required tools and dependencies for development across all SecPal repositories
  - **Global system tools:** Git, Bash, cURL, jq, REUSE, ShellCheck, yamllint, actionlint
  - **Git configuration:** user.name, user.email, GPG commit signing
  - **API repository (Laravel + DDEV):**
    - PHP 8.4+, Composer 2.x
    - DDEV (development environment) with running status check
    - PostgreSQL (via DDEV, no local install needed)
    - Laravel tools: Pest, Pint, PHPStan (checks vendor/ directory)
  - **Frontend repository (React + TypeScript):**
    - Node.js 22.x+, npm/yarn/pnpm
    - Local dependencies: TypeScript, Vite, Vitest, ESLint (checks node_modules/)
  - **Contracts repository (OpenAPI):**
    - Node.js 22.x+, npm
    - @redocly/cli (checks node_modules/)
  - **Optional tools:** GitHub CLI (gh), pre-commit, Docker, Docker Compose
  - **Features:**
    - Colored output (green ✓ / yellow ⚠ / red ✗) for visual clarity
    - Installation hints for each missing tool
    - Repository filter: `--repo=api|frontend|contracts` for targeted checks
    - Exit code 0 if all critical requirements met, 1 otherwise
    - Summary report with counts (OK / Warnings / Critical missing)
- **Documentation:** `docs/scripts/CHECK_SYSTEM_REQUIREMENTS.md` - Complete usage guide with typical scenarios (backup restore, new dev system, CI/CD integration)
- **Use case:** Essential after backup restoration or setting up new development environments to identify missing tools

**Why this matters:**

- **Multi-repo awareness:** Checks all three SecPal repositories (api, frontend, contracts) with their specific requirements
- **DDEV detection:** Special handling for API repository's DDEV environment (critical difference vs. standard PHP setup)
- **Local dependencies validation:** Not just global tools, but also checks if `composer install` / `npm install` were run
- **Zero manual debugging:** Script automatically identifies what's missing instead of trial-and-error with preflight.sh failures

---

## 2025-11-09 - Git Conflict Marker Detection

**Added automated detection for unresolved Git merge conflicts:**

- **New script:** `scripts/check-conflict-markers.sh` - Detects conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in tracked files
  - **Prevents accidental commits** of broken code with unresolved merge conflicts
  - **Checks all text files** using `git ls-files` (excludes binary files and .git directory)
  - **Clear output** showing file names and line numbers of conflicts
  - **Actionable guidance** for resolving detected conflicts
- **CI Integration:** GitHub Actions workflow `check-conflict-markers.yml` runs on all PRs and pushes to main
- **Documentation:** `docs/scripts/CHECK_CONFLICT_MARKERS.md` - Complete usage guide with examples and troubleshooting
- **Exit codes:** 0 = clean, 1 = conflicts detected
- **Use case:** Prevents syntax errors in hooks, source code, and configuration files from reaching the repository

---

## 2025-11-08 - DRY Refactoring: Copilot Instructions & YAML Enhancement

**Major refactoring to eliminate redundancy and improve AI parsing performance:**

**copilot-config.yaml - Comprehensive expansion:**

- **Checklists migrated to YAML (DRY compliance):** All checklists now in `checklists` section with validation commands
  - `pre_commit`: 7 checks (TDD, DRY, Quality, CHANGELOG, Documentation, Preflight, No Bypass)
  - `review_passes`: 4-pass strategy (Comprehensive, Deep Dive, Best Practices, Security Auditor)
  - `post_merge_cleanup`: 5-step mandatory cleanup protocol
  - `validation`: General task validation checklist
  - `copilot_proof_standard`: Quality target for zero AI suggestions
- **Workflow mapping added:** `workflows` section maps events to required checklists (before_commit, before_pr, before_merge, after_merge)
- **Multi-repository structure:** `multi_repo` section documents inheritance rules and repo-specific overrides
  - Base: `.github/` (organization-wide rules)
  - Repos: `api/`, `frontend/`, `contracts/` can override non-critical rules
  - Critical rules ALWAYS apply across all repos (TDD, 1 PR = 1 Topic, Signed Commits, REUSE, Domain Policy, Copilot Review Protocol)
  - Coordination: contracts/ FIRST, then api/frontend in parallel
- **Domain Policy:** `domain_policy` section enforces the approved SecPal host split and rejects deprecated `.app` web-host usage (ZERO TOLERANCE)
- **Bot PR Validation:** `bot_pr_validation` section codifies tech stack validation for bot-created PRs
- **Learned Lessons as Policies:** `learned_lessons` section converts retrospectives into machine-readable policies
- **🚨 CRITICAL: Copilot Review Protocol clarified:** `copilot_review.absolute_prohibition` section makes rule ultra-prominent
  - NEVER respond to Copilot comments using GitHub comment tools
  - ONLY resolve via GraphQL mutation after fixing code
  - Commenting creates unwanted bot PRs and notification spam

**copilot-instructions.md - Dramatically compressed (64% reduction):**

- **Line count:** 1019 → 368 lines (target was ≤400 lines, achieved)
- **DRY compliance:** Eliminated ~40% redundancy by referencing YAML as Single Source of Truth
- **Structure:** All checklists, validations, tech stack details now reference `copilot-config.yaml` sections
- **Improved readability:** Cleaner format with tables showing workflow-to-checklist mapping
- **Maintained completeness:** All critical information preserved, just referenced instead of duplicated

**scripts/sync-governance.sh - New automation script:**

- **Purpose:** Sync governance files from `.github/` to other repos (addresses Learned Lesson #3)
- **Files synced:** CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md, CODEOWNERS, .editorconfig, .gitattributes, scripts/check-domains.sh
- **Modes:** `sync` (copy files) and `check` (validate only)
- **Integration:** Can be added to preflight.sh for automated validation
- **Why:** Symlinks don't render on GitHub.com, files must be copied for proper display

**Impact:**

- **Parsing performance:** Estimated 3.5x faster for AI (YAML direct access vs. Markdown sequential search)
- **Maintainability:** Changes now made in 1 place (YAML) instead of 5-8 places (eliminated duplication)
- **DRY compliance:** Restored (was violating own principles with ~40% redundancy)
- **AI comprehension:** Clearer structure, unambiguous checklists, machine-readable policies
- **Multi-repo coordination:** Explicit inheritance rules prevent DRY violations across repositories

---

## 2025-11-02 - Allow Tailwind Plus License in Compatibility Check

**`reusable-license-compatibility.yml` - Added LicenseRef-TailwindPlus:**

- Added `LicenseRef-TailwindPlus` to list of AGPL-3.0-compatible licenses
- Catalyst UI Kit (Tailwind Plus) explicitly permits use in open source End Products
- License reference: <https://tailwindcss.com/plus/license>
- Components remain under Tailwind Plus License but usage in AGPL projects is allowed per license terms

---

## 2025-10-31 - Copilot Review Protocol Enhancement

**`copilot-instructions.md` - Added bot PR validation + GraphQL review resolution:**

- **GraphQL Review Resolution:** Clarified review threads MUST be resolved via GraphQL mutation (`resolveReviewThread`), NEVER via regular PR comments
- **Bot PR Validation (Lesson #11):** Added critical validation protocol for bot-created PRs (Copilot, Dependabot)
  - Auto-created PRs with pattern `copilot/sub-pr-*` require validation against tech stack
  - Reject if: redundant (duplicate of merged PR), irrelevant (suggests tech not used), out-of-scope (e.g., Rust when PHP/TS/JS only)
  - Example: Rejected Copilot PRs #155 (.github) and #45 (api) - redundant lockfile excludes + invalid JS/TS suggestions for PHP repo
- **Workflow:** Check branch name → validate tech stack → close with explanation if invalid → full review checklist if valid
- Context: Copilot auto-created PRs after review comments mentioned Cargo.lock (future-proofing suggestion) despite SecPal using no Rust

## 2025-10-28 - GitHub App Authentication Migration

**Project Board Automation migrated to GitHub App:**

- Replaced Fine-grained Personal Access Token with GitHub App authentication
- Created "SecPal" GitHub App (ID: 2196125) with organization-wide installation
- Updated all workflow callers to use `APP_ID` and `APP_PRIVATE_KEY` secrets
- Implemented dynamic token generation using `actions/create-github-app-token@v1`
- Benefits: Auto-rotating tokens, bot identity ("SecPal[bot]"), improved reliability
- Resolved cross-repository API authentication issues
- Affected workflows: `.github/workflows/project-automation-core.yml`, caller workflows in all repos

## 2025-10-23 - Copilot Instructions Optimization

**copilot-instructions.md compressed and enhanced:**

- Compressed from 1,047 lines to 393 lines (62% reduction) for AI efficiency
- Removed Change History section (historical information irrelevant for AI)
- Restructured to terse, constraint-based format (AI-only optimization)
- Added AI Self-Check Protocol with trigger events and validation checklist
- Added Multi-Repo Coordination strategy (contracts → api/frontend)
- Added Breaking Changes Process for actual software repositories
- Added CHANGELOG Maintenance guidelines
- Expanded Critical Rules from 6 to 10 (test coverage, commit signing, documentation, templates)
- Added Database Strategy (PostgreSQL prod, SQLite test, reversible migrations)
- Added API Guidelines (REST, JSON, URL versioning, JWT authentication)
- Enhanced Security section (SECURITY.md reference, response timelines)
- Made Copilot Review mandatory (was "recommended")

## 2025-01-23 - Initial Foundation

### Added

#### Documentation & Governance

- Initial repository structure and governance documentation
  - Security (responsible disclosure workflow)
  - Config/Infrastructure (build, CI/CD, dependencies)
- Issue template configuration (`.github/ISSUE_TEMPLATE/config.yml`)

#### CI/CD & Automation

- Dependabot configuration for 5 ecosystems:
  - GitHub Actions
  - npm (JavaScript/TypeScript)
  - Composer (PHP)
  - pip (Python)
  - Docker (Container images)
- Daily dependency checks at 04:00 CET
- Auto-update strategy for all version types (patch, minor, major)

#### Quality Standards

- REUSE 3.3 compliance setup with SPDX headers
- Documentation for REUSE.toml (replacing deprecated .reuse/dep5)
- Pre-commit and pre-push hook guidelines
- Comprehensive linting standards (Prettier, Markdownlint, ESLint, PHPStan)

#### Technology Stack Documentation

- Backend: Laravel 12, PHP 8.4, Pest, PHPStan (level: max)
- Frontend: React, Node 22.x, TypeScript (strict), Vite, ESLint, Vitest
- API: OpenAPI 3.1 as single source of truth
- Version Control: Git with signed commits, linear history

### Changed

- Nothing (initial release)

### Security

- Secret scanning enabled with push protection
- Dependabot security updates prioritized
- CodeQL analysis configured (JavaScript/TypeScript only, PHP excluded)
- Branch protection enforced with required status checks
- All repositories public by default (AGPL compliance, transparency)

### Notes

This is the foundational release establishing:

- Project governance and contribution workflows
- Quality gates and testing philosophy (TDD mandatory)
- Licensing strategy (AGPL-3.0-or-later for code, CC0-1.0 for config/docs, MIT for scripts)
- Security-first development practices
- Semantic Versioning commitment starting at 0.0.1

**Development Phase:** This is a 0.x.x release. APIs may change without notice. Breaking changes are allowed in minor version bumps. No backward compatibility guarantees until 1.0.0.

**Open Discussions:**

- [Issue #36](https://github.com/SecPal/.github/issues/36): Dependabot auto-merge implementation strategy
- [Issue #37](https://github.com/SecPal/.github/issues/37): Dependabot check frequency (daily vs weekly)
- [Issue #38](https://github.com/SecPal/.github/issues/38): AGPL-3.0-or-later license strategy review
- [Issue #39](https://github.com/SecPal/.github/issues/39): TDD mandatory policy vs exploration exceptions
