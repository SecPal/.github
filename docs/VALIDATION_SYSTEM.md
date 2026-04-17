<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Validation System for Copilot Instructions

## Overview

The validation system ensures that Copilot instructions maintain quality,
consistency, and repository-specific AI-risk guidance across all SecPal
repositories: `.github`, `api`, `frontend`, `contracts`, `android`,
`secpal.app`, and `changelog`.

## Architecture

### Components

```
.github/
├── scripts/
│   ├── validate-copilot-instructions.sh  # Main validation script
│   └── README.md                          # Script documentation
├── tests/
│   └── validate-copilot-instructions.sh   # Validator regression coverage
├── .github/
│   ├── copilot-instructions.md            # Markdown instructions (authoritative)
│   └── workflows/
│       ├── reusable-copilot-instructions.yml  # Shared CI workflow
│       └── validate-copilot-instructions.yml  # .github repo caller workflow
└── docs/
    └── VALIDATION_SYSTEM.md               # This document

> **Note:** `.github/copilot-config.yaml` was permanently removed on 2026-04-11.
> Governance baseline is now fully in `copilot-instructions.md` and per-repo instruction files.
```

### Validation Script

**Location:** `scripts/validate-copilot-instructions.sh`

**Purpose:** Automated testing of Copilot instructions quality and required AI-risk guidance

**Features:**

- Repository-aware (detects `.github`, `api`, `frontend`, `contracts`, `android`, `secpal.app`, and `changelog`)
- generic AI triage validation plus repository-specific known-risk checks
- regression coverage for validator guardrails and repo detection
- Color-coded output
- Exit codes for CI integration
- Optional dependency handling

### CI Workflow

**Locations:** `.github/workflows/reusable-copilot-instructions.yml` and `.github/workflows/validate-copilot-instructions.yml`

**Triggers:**

- Push to `main` (org repo caller, when instruction files change)
- Pull requests (org repo caller, when instruction files change)
- Manual dispatch
- Reusable workflow calls from sibling-repository `quality.yml` workflows

**Steps:**

1. Checkout the caller repository
2. Checkout `SecPal/.github` when the caller is a sibling repository
3. Setup Node.js 22 and install `markdownlint-cli2`
4. Run `scripts/validate-copilot-instructions.sh`
5. Fail the caller workflow when required guidance is missing

## Test Cases

The validator enforces file presence, REUSE compliance, markdown quality,
runtime-model guidance, generic AI-triage guardrails, repository-specific
known-risk patterns, and required frontmatter for file-based instruction
overlays.

### 1. File Existence

**Purpose:** Ensure required files exist

**Files Checked:**

- `.github/copilot-instructions.md` (required)

**Failure Impact:** CRITICAL - Instructions missing

### 2. YAML Config Existence

**Purpose:** Check for YAML configuration (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` has been permanently removed. No Copilot mechanism reads this file;
governance baseline is in `copilot-instructions.md` and per-repo instruction files. This test
always skips.

**Failure Impact:** N/A - File removed

### 3. Instructions REUSE Compliance

**Purpose:** Validate REUSE licensing for instructions

**Files Checked:**

- `.github/copilot-instructions.md.license`
- Allowed license identifiers: `CC0-1.0` or `AGPL-3.0-or-later`

**Failure Impact:** CRITICAL - REUSE compliance required

### 4. YAML Config REUSE Compliance

**Purpose:** Validate REUSE licensing for YAML config (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` and its `.license` sidecar have been permanently removed.
This test always skips.

**Failure Impact:** N/A - File removed

### 5. Markdown Linting

**Purpose:** Ensure markdown quality standards

**Tool:** markdownlint-cli2

**Config:** `.markdownlint.json` (repo-specific)

**Checks:**

- Line lengths (240/.github, 400/api, 120/frontend+contracts)
- Heading styles
- List formatting
- Code block fences

**Failure Impact:** MEDIUM - Quality standards

**Auto-fix:** `npx markdownlint-cli2 .github/copilot-instructions.md --fix`

### 6. YAML Syntax Validation

**Purpose:** Ensure YAML is parseable (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` has been permanently removed. This test always skips.

**Failure Impact:** N/A - File removed

### 7. @EXTENDS Reference

**Purpose:** Verify inheritance structure

**Logic:**

- Org-level (.github): Skip test
- Repo-level (api/frontend/contracts): Check for `@EXTENDS`

**Failure Impact:** MEDIUM - Best practice for DRY

### 8. Critical Rules Presence

**Purpose:** Ensure core principles documented

**Search Pattern:** `critical[[:space:]]+rules|core[[:space:]]+principles` (requires at least one space between words)

**Failure Impact:** HIGH - Missing essential content

## Repository-Specific Behavior

### .github Repository (Org-Level)

```bash
Repository Type: org

✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - removed 2026-04-11)
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - removed 2026-04-11)
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - removed 2026-04-11)
✓ repo-specific instructions use @EXTENDS (Skipped - org-level)
✓ instructions contain critical rules
```

### api Repository (Laravel)

```bash
Repository Type: api

✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - optional)
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - not present)
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - not present)
✓ repo-specific instructions use @EXTENDS
✓ instructions contain critical rules
```

### frontend Repository (React)

Similar to api, detects via `package.json` with `vite`

### contracts Repository (OpenAPI)

Similar to api, detects via `package.json` with `openapi` or `docs/openapi.yaml`

## Integration Points

### Pre-commit Hooks

**Not integrated** - Instructions changes are rare, CI-only validation sufficient

### Pre-push Hooks

**Not integrated** - Instructions changes are rare, CI-only validation sufficient

### GitHub Actions

**Integrated** - Runs on every push/PR affecting instruction files

**Status Check:** Required for merging

### Manual Execution

```bash
# Run in any repository
./scripts/validate-copilot-instructions.sh

# Exit code 0 = success, 1 = failure
```

## Failure Resolution

### Test 1 Failed: Instructions Missing

```bash
# Create instructions file with license
touch .github/copilot-instructions.md
cat > .github/copilot-instructions.md.license << 'EOF'
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
EOF
```

### Test 3/4 Failed: REUSE Compliance

```bash
# Create license file with SPDX headers
cat > .github/copilot-instructions.md.license << 'EOF'
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
EOF
```

### Test 5 Failed: Markdown Linting

```bash
# Auto-fix markdown issues
npx markdownlint-cli2 .github/copilot-instructions.md --fix

# Manual review
npx markdownlint-cli2 .github/copilot-instructions.md
```

### Test 6 Failed: YAML Syntax

This test always skips as of 2026-04-11 because `.github/copilot-config.yaml` has been permanently
removed from the repository.

### Test 7 Failed: Missing @EXTENDS

```bash
# Add @EXTENDS reference to repo-specific instructions
cat <<'EOF' >> .github/copilot-instructions.md

@EXTENDS .github repository instructions
EOF
```

### Test 8 Failed: Missing Critical Rules

```bash
# Add critical rules section to instructions
# See .github/copilot-instructions.md for template
```

## Metrics

### Success Criteria

- All 8 tests pass
- Exit code 0
- Green CI status

### Performance

- **Execution Time:** ~5-10 seconds
- **CI Time:** ~30-45 seconds (including setup)

### Coverage

- 4 repositories (.github, api, frontend, contracts)
- 2 file formats (Markdown, YAML)
- 3 quality dimensions (existence, licensing, syntax)

## Future Enhancements

### Phase 1 (Current)

- ✅ Basic validation script
- ✅ CI integration
- ✅ Repository detection
- ✅ REUSE compliance checks

### Phase 2 (Planned)

- Content validation (check for required sections)
- YAML schema validation (validate structure)
- Cross-repo consistency checks
- Automated fix suggestions

### Phase 3 (Future)

- Pre-commit hook integration (optional)
- Dependency graph validation
- Performance benchmarking
- Automated updates from template

## Troubleshooting

### Script Not Executable

```bash
chmod +x scripts/validate-copilot-instructions.sh
```

### markdownlint-cli2 Not Found

```bash
npm install -g markdownlint-cli2
```

### Ruby Not Found

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ruby

# macOS
brew install ruby
```

### False Positive on @EXTENDS

Repository detection may fail if:

- Multiple `package.json` files exist
- Repository structure is non-standard

Manual override:

```bash
# Force repository type
REPO_TYPE=api ./scripts/validate-copilot-instructions.sh
```

## Maintenance

### Adding New Tests

1. Add test function to `validate-copilot-instructions.sh`
2. Call function in `main()`
3. Update test count expectations
4. Document in this file
5. Update scripts/README.md

Current instruction-content checks include runtime-model guidance, critical rules, and AI findings triage language so
repo baselines keep requiring proof-of-defect review for AI-generated suggestions.

The validator also accepts either inline SPDX headers or companion `.license` sidecars for `copilot-instructions.md`,
but when a `.license` sidecar is present it must still be valid and consistent with any inline SPDX metadata. Its
pseudo-inheritance check is intentionally scoped to positive inheritance directives so repo-local "do not inherit"
guidance does not trigger false positives.

### Updating Test Logic

1. Modify test function
2. Test locally in all 4 repos
3. Update documentation
4. Commit with clear explanation

### Deprecating Tests

1. Mark as deprecated in script comments
2. Update documentation
3. Remove after 1 release cycle

## License

This validation system is licensed under MIT.
See `scripts/validate-copilot-instructions.sh.license` for details.
