<!--
SPDX-FileCopyrightText: 2025-2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Validation System for AI Instructions

## Overview

The validation system ensures that AI instructions maintain quality,
consistency, and repository-specific AI-risk guidance across all managed
SecPal repositories: `.github`, `api`, `frontend`, `contracts`, `android`,
`secpal.app`, `changelog`, `GuardGuide`, and `guardguide.de`.

## Architecture

### Components

```
.github/
├── scripts/
│   ├── validate-ai-instructions.sh  # Main validation script
│   └── README.md                          # Script documentation
├── tests/
│   └── validate-ai-instructions.sh   # Validator regression coverage
├── .github/
│   ├── AGENTS.md                          # Authoritative runtime baseline
│   ├── copilot-instructions.md            # Compatibility mirror
│   └── workflows/
│       ├── reusable-ai-instructions.yml  # Shared CI workflow
│       └── validate-ai-instructions.yml  # .github repo caller workflow
└── docs/
    └── VALIDATION_SYSTEM.md               # This document

> **Note:** `.github/copilot-config.yaml` was permanently removed on 2026-04-11.
> Each repository's authoritative AI baseline lives in `AGENTS.md`. The `.github/copilot-instructions.md` file is a compatibility mirror for tooling that auto-loads that path, and per-repo `.github/instructions/*.instructions.md` files remain focused overlays where needed.
```

### Validation Script

**Location:** `scripts/validate-ai-instructions.sh`

**Purpose:** Automated testing of AI-instruction quality and required AI-risk guidance

**Features:**

- Repository-aware (detects `.github`, `api`, `frontend`, `contracts`, `android`, `secpal.app`, `changelog`, `GuardGuide`, and `guardguide.de`)
- generic AI triage validation plus repository-specific known-risk checks
- regression coverage for validator guardrails and repo detection
- Color-coded output
- Exit codes for CI integration
- Optional dependency handling

### CI Workflow

**Locations:** `.github/workflows/reusable-ai-instructions.yml` and `.github/workflows/validate-ai-instructions.yml`

**Triggers:**

- Push to `main` (org repo caller, when instruction files change)
- Pull requests (org repo caller, when instruction files change)
- Manual dispatch
- Reusable workflow calls from sibling-repository `quality.yml` workflows

**Steps:**

1. Checkout the caller repository
2. Checkout `SecPal/.github` when the caller is a sibling repository
3. Setup Node.js 22 and run `npm ci` in `SecPal/.github`
4. Run `scripts/validate-ai-instructions.sh`
5. Fail the caller workflow when required guidance is missing

## Test Cases

The validator enforces file presence, REUSE compliance, markdown quality,
runtime-model guidance, `AGENTS.md` size limits, generic AI-triage guardrails,
provider-neutral review guidelines, repository-specific known-risk patterns,
and required frontmatter for file-based instruction overlays.

### 1. File Existence

**Purpose:** Ensure required files exist

**Files Checked:**

- `AGENTS.md` (required authoritative runtime baseline)
- `.github/copilot-instructions.md` (required compatibility mirror)

**Failure Impact:** CRITICAL - Instructions missing

### 2. YAML Config Existence

**Purpose:** Check for YAML configuration (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` has been permanently removed. No Copilot mechanism reads this file;
governance baseline is in `AGENTS.md`, with `.github/copilot-instructions.md` mirroring it for Copilot-compatible tooling and `.github/instructions/*.instructions.md` providing focused overlays where supported. This test
always skips.

**Failure Impact:** N/A - File removed

### 3. Instructions REUSE Compliance

**Purpose:** Validate REUSE licensing for instructions

**Files Checked:**

- `AGENTS.md` and `.github/copilot-instructions.md`
- REUSE metadata may be provided via inline SPDX headers or companion `.license` sidecars
- Allowed license identifiers: `CC0-1.0` or `AGPL-3.0-or-later`

**Failure Impact:** CRITICAL - REUSE compliance required

### 4. YAML Config REUSE Compliance

**Purpose:** Validate REUSE licensing for YAML config (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` and its `.license` sidecar have been permanently removed.
This test always skips.

**Failure Impact:** N/A - File removed

### 5. Markdown Linting

**Purpose:** Ensure markdown quality standards

**Tool:** markdownlint-cli

**Config:** `.markdownlint.json` (repo-specific)

**Checks:**

- Line lengths (240/.github, 400/api, 120/frontend+contracts)
- Heading styles
- List formatting
- Code block fences

**Failure Impact:** MEDIUM - Quality standards

**Auto-fix:** `./node_modules/.bin/markdownlint --config .markdownlint.json AGENTS.md .github/copilot-instructions.md --fix`

### Audit Status

`SecPal/.github` now pins `markdownlint-cli@0.49.0` locally so markdown
linting stays reproducible after `npm ci` without depending on the
`markdownlint-cli2` package graph that kept the remaining moderate
`npm audit` findings open.

### 6. Legacy YAML Syntax Validation

**Purpose:** Ensure YAML is parseable (removed as of 2026-04-11)

**Note:** `.github/copilot-config.yaml` has been permanently removed. This test always skips.

**Failure Impact:** N/A - File removed

### 7. Runtime Model Validation

**Purpose:** Verify that `AGENTS.md` is the authoritative runtime baseline and
that `.github/copilot-instructions.md` remains a compatibility mirror.

**Logic:**

- Org-level (.github): require authoritative runtime wording
- Repo-level: require self-contained `AGENTS.md` guidance plus mirror contract

**Failure Impact:** HIGH - runtime model drift

### 8. Critical Rules Presence

**Purpose:** Ensure core principles documented

**Search Pattern:** `critical[[:space:]]+rules|core[[:space:]]+principles` (requires at least one space between words)

**Failure Impact:** HIGH - Missing essential content

### 9. `AGENTS.md` Size Limit

**Purpose:** Keep the authoritative runtime baseline below the default
project-instruction discovery budget used by current AI tooling.

**Limit:** 32768 bytes

**Failure Impact:** HIGH - Instructions may be truncated at runtime

### 10. AI Findings Triage

**Purpose:** Ensure AI-generated findings remain hints until proven by a test,
reproduction, or violated invariant.

**Failure Impact:** HIGH - AI output could be merged without proof

### 11. Provider-Neutral Review Guidelines

**Purpose:** Ensure every repository has explicit review guidance that works
for any AI reviewer and rejects AI self-reference, generated-by text, tool
promotion, and attribution.

**Failure Impact:** HIGH - AI reviews may drift into provider-specific or
self-promotional behavior

## Repository-Specific Behavior

### .github Repository (Org-Level)

```bash
Repository Type: org

✓ AGENTS.md exists
✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - removed 2026-04-11)
✓ AGENTS.md has REUSE license
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - removed 2026-04-11)
✓ AGENTS.md passes markdown lint
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - removed 2026-04-11)
✓ org instructions define runtime model
✓ instructions contain critical rules
```

### api Repository (Laravel)

```bash
Repository Type: api

✓ AGENTS.md exists
✓ copilot-instructions.md exists
✓ copilot-config.yaml exists (Skipped - optional)
✓ AGENTS.md has REUSE license
✓ copilot-instructions.md has REUSE license
✓ copilot-config.yaml has REUSE license (Skipped - not present)
✓ AGENTS.md passes markdown lint
✓ copilot-instructions.md passes markdown lint
✓ copilot-config.yaml has valid syntax (Skipped - not present)
✓ repo instructions are self-contained
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
./scripts/validate-ai-instructions.sh

# Exit code 0 = success, 1 = failure
```

## Failure Resolution

### Test 1 Failed: Instructions Missing

```bash
# Create the authoritative baseline first
cat > AGENTS.md << 'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Repository Agent Instructions

This file is the authoritative, provider-neutral runtime baseline for this repository.
EOF

# Then create or regenerate the compatibility mirror
cp AGENTS.md .github/copilot-instructions.md
```

### Test 3/4 Failed: REUSE Compliance

```bash
# Add inline SPDX headers or create matching .license sidecars
cat > AGENTS.md.license << 'EOF'
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
EOF

cat > .github/copilot-instructions.md.license << 'EOF'
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
EOF
```

### Test 5 Failed: Markdown Linting

```bash
# Auto-fix markdown issues
./node_modules/.bin/markdownlint --config .markdownlint.json AGENTS.md .github/copilot-instructions.md --fix

# Manual review
./node_modules/.bin/markdownlint --config .markdownlint.json AGENTS.md .github/copilot-instructions.md
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
# Start from AGENTS.md as the authoritative template
```

## Metrics

### Success Criteria

- All 18 tests pass
- Exit code 0
- Green CI status

### Performance

- **Execution Time:** ~5-10 seconds
- **CI Time:** ~30-45 seconds (including setup)

### Coverage

- 9 managed repositories (`.github`, `api`, `frontend`, `contracts`, `android`, `secpal.app`, `changelog`, `GuardGuide`, `guardguide.de`)
- 2 instruction surfaces (authoritative `AGENTS.md` plus compatibility mirror)
- 6 quality dimensions (existence, REUSE compliance, markdown quality, runtime-model integrity, size safety, content guardrails)

## Future Enhancements

### Phase 1 (Current)

- ✅ Basic validation script
- ✅ CI integration
- ✅ Repository detection
- ✅ REUSE compliance checks

### Phase 2 (Planned)

- Deeper semantic validation for repo-specific instruction drift
- Cross-repo consistency checks beyond required baseline guardrails
- Additional automated checks for overlay-to-baseline alignment
- Automated fix suggestions

### Phase 3 (Future)

- Pre-commit hook integration (optional)
- Dependency graph validation
- Performance benchmarking
- Automated updates from template

## Troubleshooting

### Script Not Executable

```bash
chmod +x scripts/validate-ai-instructions.sh
```

### markdownlint-cli Not Found

```bash
npm ci
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
REPO_TYPE=api ./scripts/validate-ai-instructions.sh
```

## Maintenance

### Adding New Tests

1. Add test function to `validate-ai-instructions.sh`
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
See `scripts/validate-ai-instructions.sh.license` for details.
