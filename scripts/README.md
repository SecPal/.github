<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

## Validation Scripts

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

### `validate-copilot-instructions.sh`

Validates Copilot instructions and configuration files across all repositories.

**Usage:**

```bash
# In any repository (.github, api, frontend, contracts)
./scripts/validate-copilot-instructions.sh
```

**Tests Performed:**

1. **File Existence**

   - Checks for `copilot-instructions.md`
   - `copilot-config.yaml` check always skips (file removed 2026-04-11)

2. **REUSE Compliance**

   - Validates `copilot-instructions.md.license` exists
   - `copilot-config.yaml.license` check always skips (file removed 2026-04-11)
   - Verifies CC0-1.0 license

3. **Markdown Linting**

   - Runs markdownlint-cli2 on instructions
   - Suggests auto-fix command on failure

4. **YAML Syntax**

   - Validates YAML syntax using yq
   - Skips if yq not installed

5. **Inheritance Check**

   - Verifies `@EXTENDS` reference in repo-specific instructions
   - Skips for org-level instructions

6. **Content Validation**
   - Ensures critical rules/principles section exists
   - Ensures AI findings triage guidance exists
   - Validates core content presence

**Exit Codes:**

- `0`: All tests passed
- `1`: One or more tests failed

**Example Output:**

```
=========================================
Copilot Instructions Validation
=========================================

Repository Type: api

✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - removed 2026-04-11)
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - removed 2026-04-11)
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - removed 2026-04-11)
✓ repo-specific instructions use @EXTENDS
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

See `.github/workflows/validate-copilot-instructions.yml`

**Dependencies:**

- `bash` (required)
- `grep` (required)
- `npx markdownlint-cli2` (optional, for markdown linting)
- `yq` (optional, for YAML validation)

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
bash scripts/sync-required-checks.sh --repo GuardGuide --print-payload | jq

# Apply the configured payload to one repository
bash scripts/sync-required-checks.sh --repo api --apply

# Apply the configured payloads to every managed repository
bash scripts/sync-required-checks.sh --apply
```

**Managed Repositories:**

- `api`
- `changelog`
- `frontend`
- `contracts`
- `android`
- `secpal.app`
- `GuardGuide`

**What It Does:**

1. Defines the required status-check contexts per repository in one manifest
2. Builds the exact JSON payload GitHub expects for branch protection updates
3. Applies the payload through `gh api` using `--input` so booleans and arrays stay typed correctly
4. Keeps the live branch-protection baseline repeatable after workflow or context drift

**Exit Codes:**

- `0`: Payload printed or sync applied successfully
- `2`: Usage error, unknown repository, or missing dependency

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
