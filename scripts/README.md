<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Scripts

This directory contains utility scripts for SecPal development.

## Validation Scripts

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
   - Checks for `copilot-config.yaml` (optional)

2. **REUSE Compliance**
   - Validates `copilot-instructions.md.license` exists
   - Validates `copilot-config.yaml.license` exists (if YAML present)
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
✓ copilot-config.yaml exists
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax
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
- **frontend**: React frontend (has `package.json` with `vite`)
- **contracts**: OpenAPI contracts (has `package.json` with `openapi`)

## Adding New Scripts

When adding new scripts:

1. Include SPDX headers in script file
2. Create `.license` file for REUSE compliance
3. Make scripts executable: `chmod +x scripts/your-script.sh`
4. Document usage in this README
5. Add CI workflow if appropriate
6. Test across all 4 repositories

## License

All scripts use MIT License unless otherwise specified.
See individual `.license` files for details.
