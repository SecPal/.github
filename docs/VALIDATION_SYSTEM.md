<!--
SPDX-FileCopyrightText: 2025 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Validation System for Copilot Instructions

## Overview

The Validation System ensures that Copilot instructions and configuration files maintain quality and consistency across all SecPal repositories (.github, api, frontend, contracts).

## Architecture

### Components

```
.github/
├── scripts/
│   ├── validate-copilot-instructions.sh  # Main validation script
│   └── README.md                          # Script documentation
├── .github/
│   ├── copilot-instructions.md            # Markdown instructions
│   ├── copilot-config.yaml                # YAML configuration
│   └── workflows/
│       └── validate-copilot-instructions.yml  # CI workflow
└── docs/
    └── VALIDATION_SYSTEM.md               # This document
```

### Validation Script

**Location:** `scripts/validate-copilot-instructions.sh`

**Purpose:** Automated testing of Copilot instructions quality

**Features:**

- Repository-aware (detects .github, api, frontend, contracts)
- 8 comprehensive test cases
- Color-coded output
- Exit codes for CI integration
- Optional dependency handling

### CI Workflow

**Location:** `.github/workflows/validate-copilot-instructions.yml`

**Triggers:**

- Push to `main` (when instruction files change)
- Pull requests (when instruction files change)
- Manual dispatch

**Steps:**

1. Checkout repository
2. Setup Node.js 20
3. Install markdownlint-cli2
4. Install yq (YAML processor)
5. Run validation script
6. Report summary

## Test Cases

### 1. File Existence

**Purpose:** Ensure required files exist

**Files Checked:**

- `.github/copilot-instructions.md` (required)
- `.github/copilot-config.yaml` (optional)

**Failure Impact:** CRITICAL - Instructions missing

### 2. YAML Config Existence

**Purpose:** Check for YAML configuration (optional enhancement)

**Files Checked:**

- `.github/copilot-config.yaml`

**Failure Impact:** LOW - YAML is optional

### 3. Instructions REUSE Compliance

**Purpose:** Validate REUSE licensing for instructions

**Files Checked:**

- `.github/copilot-instructions.md.license`
- License identifier: `CC0-1.0`

**Failure Impact:** CRITICAL - REUSE compliance required

### 4. YAML Config REUSE Compliance

**Purpose:** Validate REUSE licensing for YAML config

**Files Checked:**

- `.github/copilot-config.yaml.license`
- License identifier: `CC0-1.0`

**Failure Impact:** CRITICAL (if YAML present) - REUSE compliance required

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

**Purpose:** Ensure YAML is parseable

**Tool:** yq

**Test:** Parse `.version` key

**Failure Impact:** CRITICAL (if YAML present) - Invalid YAML

### 7. @EXTENDS Reference

**Purpose:** Verify inheritance structure

**Logic:**

- Org-level (.github): Skip test
- Repo-level (api/frontend/contracts): Check for `@EXTENDS`

**Failure Impact:** MEDIUM - Best practice for DRY

### 8. Critical Rules Presence

**Purpose:** Ensure core principles documented

**Search Pattern:** `critical[[:space:]]*rules|core[[:space:]]*principles` (matches variants, not just exact phrases)

**Failure Impact:** HIGH - Missing essential content

## Repository-Specific Behavior

### .github Repository (Org-Level)

```bash
Repository Type: org

✓ copilot-instructions.md exists
✓ copilot-config.yaml exists
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax
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

Similar to api, detects via `package.json` with `openapi`

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

```bash
# Check YAML syntax
yq eval '.version' .github/copilot-config.yaml

# Common issues:
# - Incorrect indentation
# - Missing colons
# - Unclosed quotes
```

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

### yq Not Found

```bash
# Linux
sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
sudo chmod +x /usr/local/bin/yq

# macOS
brew install yq
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
