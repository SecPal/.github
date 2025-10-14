<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# SecPal Repository Setup Guide

**Purpose:** Standardized setup checklist for all new SecPal repositories

**Target Audience:** Developers creating new repositories in the SecPal organization

---

## ✅ Mandatory Setup Checklist

Use this checklist for **every new repository** to ensure consistency and quality.

---

### 1. Repository Creation

```bash
# Create repository (choose visibility as needed)
gh repo create SecPal/<repo-name> --public --clone

cd <repo-name>

# Create initial structure
mkdir -p .github/workflows
mkdir -p docs
mkdir -p scripts
```

---

### 2. License & REUSE Compliance

```bash
# Add LICENSE file (SecPal standard: AGPL-3.0-or-later)
curl -o LICENSE https://raw.githubusercontent.com/SecPal/.github/main/LICENSES/AGPL-3.0-or-later.txt

# Add REUSE.toml
cat > REUSE.toml <<'EOF'
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: CC0-1.0

version = 1
SPDX-PackageName = "<repo-name>"
SPDX-PackageSupplier = "SecPal Contributors"
SPDX-PackageDownloadLocation = "https://github.com/SecPal/<repo-name>"

[[annotations]]
path = ["package-lock.json", ".prettierrc", ".prettierignore", ".gitignore", "tsconfig.json"]
precedence = "aggregate"
SPDX-FileCopyrightText = "2025 SecPal Contributors"
SPDX-License-Identifier = "CC0-1.0"
EOF

# Create LICENSES directory
mkdir -p LICENSES
curl -o LICENSES/AGPL-3.0-or-later.txt https://www.gnu.org/licenses/agpl-3.0.txt
```

---

### 3. Pre-Commit Hook (Lesson #17 Enforcement)

```bash
# Install pre-commit hook
curl -o .git/hooks/pre-commit https://raw.githubusercontent.com/SecPal/.github/main/.github/templates/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Verify installation
ls -lah .git/hooks/pre-commit
# Should show: -rwxr-xr-x
```

**What it does:**

- ✅ Prevents whitespace errors
- ✅ Enforces code formatting (Prettier)
- ✅ Catches unstaged changes (Lesson #17)

**See:** [Pre-Commit Hook Installation Guide](../.github/templates/hooks/INSTALLATION.md)

---

### 4. Prettier Configuration

```bash
# Copy Prettier config from .github repo
curl -o .prettierrc https://raw.githubusercontent.com/SecPal/.github/main/.prettierrc
curl -o .prettierignore https://raw.githubusercontent.com/SecPal/.github/main/.prettierignore
```

---

### 5. License Policy Configuration (Lesson #15)

```bash
# Create .license-policy.json
# Choose appropriate template based on project type:

# For most projects (permissive only):
cat > .license-policy.json <<'EOF'
{
  "allowedLicenses": [
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "CC0-1.0",
    "Unlicense"
  ],
  "deniedLicenses": [
    "GPL-2.0",
    "LGPL-2.0",
    "LGPL-2.1",
    "AGPL-1.0"
  ],
  "description": "Permissive licenses compatible with AGPL-3.0-or-later"
}
EOF

# For projects that can use GPL/LGPL dependencies:
cat > .license-policy.json <<'EOF'
{
  "allowedLicenses": [
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "CC0-1.0",
    "Unlicense",
    "GPL-3.0-or-later",
    "LGPL-3.0-or-later",
    "AGPL-3.0-or-later"
  ],
  "deniedLicenses": [
    "GPL-2.0",
    "LGPL-2.0",
    "LGPL-2.1",
    "AGPL-1.0"
  ],
  "description": "AGPL-3.0-or-later compatible licenses"
}
EOF
```

---

### 6. GitHub Workflows (Required)

Create `.github/workflows/` with standard workflows:

#### A. Code Formatting Check

```yaml
# .github/workflows/format.yml
name: Code Formatting

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  format:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-node@v5
        with:
          node-version: "22"
          cache: "npm"

      - run: npm ci

      - name: Check formatting
        run: npm run format:check
```

#### B. REUSE Compliance

```yaml
# .github/workflows/reuse.yml
name: REUSE Compliance

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  reuse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: REUSE Compliance Check
        uses: fsfe/reuse-action@v6
```

#### C. License Compatibility Check

```yaml
# .github/workflows/license-check.yml
name: License Compatibility Check

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  check-licenses:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-node@v5
        with:
          node-version: "22"
          cache: "npm"

      - run: npm ci

      - name: Check license compatibility
        run: bash scripts/check-licenses.sh
```

Create the script:

```bash
# scripts/check-licenses.sh
#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -e

# Check if .license-policy.json exists
if [ ! -f .license-policy.json ]; then
  echo "No .license-policy.json found, skipping license check."
  exit 0
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
  echo "Error: jq is required but not installed!" >&2
  exit 1
fi

# Validate JSON is well-formed
if ! jq empty .license-policy.json > /dev/null 2>&1; then
  echo "Error: .license-policy.json is malformed (invalid JSON)." >&2
  exit 1
fi

# Check for allowedLicenses key
if ! jq -e 'has("allowedLicenses") and (.allowedLicenses != null)' .license-policy.json > /dev/null 2>&1; then
  echo "Error: 'allowedLicenses' key is missing or null in .license-policy.json." >&2
  exit 1
fi

ALLOWED=$(jq -r '.allowedLicenses | join(";")' .license-policy.json)

# Verify allowedLicenses is not empty
if [ -z "$ALLOWED" ]; then
  echo "Error: 'allowedLicenses' is empty in .license-policy.json." >&2
  exit 1
fi

npx license-checker --production --onlyAllow "$ALLOWED" --summary

chmod +x scripts/check-licenses.sh
```

#### D. Dependency Review

```yaml
# .github/workflows/dependency-review.yml
name: Dependency Review

on:
  pull_request:
    branches: [main, develop]

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Load license policy
        id: policy
        run: |
          if [ ! -f .license-policy.json ]; then
            echo "Error: .license-policy.json not found!" >&2
            exit 1
          fi
          DENIED=$(jq -r '.deniedLicenses | join(", ")' .license-policy.json)
          if [ -z "$DENIED" ]; then
            echo "Error: deniedLicenses is empty in .license-policy.json!" >&2
            exit 1
          fi
          echo "denied=$DENIED" >> $GITHUB_OUTPUT

      - name: Dependency Review
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: moderate
          deny-licenses: ${{ steps.policy.outputs.denied }}
```

#### E. Signed Commits Verification

```yaml
# .github/workflows/signed-commits.yml
name: Verify Signed Commits

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  verify-commits:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Verify all commits are signed
        run: |
          echo "🔍 Verifying commit signatures..."

          if [ "${{ github.event_name }}" = "pull_request" ]; then
            COMMITS=$(git rev-list origin/${{ github.base_ref }}..${{ github.sha }})
          else
            COMMITS=$(git rev-list ${{ github.sha }} -n 20)
          fi

          UNSIGNED=()
          for commit in $COMMITS; do
            if ! git verify-commit $commit 2>/dev/null; then
              UNSIGNED+=($commit)
            fi
          done

          if [ ${#UNSIGNED[@]} -gt 0 ]; then
            echo "❌ Found unsigned commits:"
            for commit in "${UNSIGNED[@]}"; do
              git log --format="%H %s" -n 1 $commit
            done
            exit 1
          fi

          echo "✅ All commits are signed"
```

---

### 7. Branch Protection Rules

```bash
# Set up branch protection for main
gh api repos/SecPal/<repo-name>/branches/main/protection \
  -X PUT \
  -f enforce_admins=true \
  -f required_pull_request_reviews[required_approving_review_count]=0 \
  -f required_status_checks[strict]=true \
  --field required_status_checks.contexts[]="Code Formatting" \
  --field required_status_checks.contexts[]="REUSE Compliance" \
  --field required_status_checks.contexts[]="Verify Signed Commits"
```

Or use the GitHub UI:

- Settings → Branches → Add rule
- Branch name pattern: `main`
- ✅ Require status checks to pass before merging
  - ✅ Code Formatting
  - ✅ REUSE Compliance
  - ✅ Verify Signed Commits
- ✅ Require branches to be up to date before merging

---

### 8. Package.json Setup (Node.js Projects)

```json
{
  "name": "<repo-name>",
  "version": "0.1.0",
  "description": "SecPal <description>",
  "main": "src/index.ts",
  "scripts": {
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest",
    "build": "tsc",
    "lint": "eslint ."
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/SecPal/<repo-name>.git"
  },
  "author": "SecPal Contributors",
  "license": "AGPL-3.0-or-later",
  "devDependencies": {
    "prettier": "^3.0.0",
    "typescript": "^5.0.0",
    "vitest": "^1.0.0"
  }
}
```

---

### 9. README.md Template

```markdown
<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# <Repo Name>

> [Brief description of what this repository does]

## Features

- Feature 1
- Feature 2
- Feature 3

## Installation

\`\`\`bash
npm install
\`\`\`

## Usage

\`\`\`bash
npm run dev
\`\`\`

## Development

### Prerequisites

- Node.js 22+
- npm 10+

### Setup

\`\`\`bash

# Clone repository

git clone https://github.com/SecPal/<repo-name>.git
cd <repo-name>

# Install dependencies

npm install

# Install pre-commit hook (important!)

cp /path/to/.github/.github/templates/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
\`\`\`

### Code Quality

\`\`\`bash

# Format code

npm run format

# Check formatting

npm run format:check

# Run tests

npm test

# Check license compatibility

bash scripts/check-licenses.sh
\`\`\`

## Contributing

See [CONTRIBUTING.md](https://github.com/SecPal/.github/blob/main/docs/CONTRIBUTING.md)

## License

AGPL-3.0-or-later - See [LICENSE](./LICENSE)

## Organization Documentation

For comprehensive guidelines, audit findings, and lessons learned:

- [Lessons Learned](https://github.com/SecPal/.github/blob/main/docs/LESSONS-LEARNED-CONTRACTS-REPO.md)
- [Audit Report](https://github.com/SecPal/.github/blob/main/docs/AUDIT-REPORT-2025-10-12.md)
- [Prevention Strategy](https://github.com/SecPal/.github/blob/main/docs/PREVENTION-STRATEGY.md)
```

---

## Technology-Specific Additions

### For React Projects

```bash
# Additional dependencies
npm install --save-dev @types/react @types/react-dom

# Vite config
npm create vite@latest . -- --template react-ts
```

### For Laravel Projects

```bash
# Use Laravel installer
composer create-project laravel/laravel .

# Add Prettier for Blade templates
npm install --save-dev prettier @shufo/prettier-plugin-blade

# Update package.json scripts
{
  "scripts": {
    "format": "prettier --write 'resources/**/*.blade.php'",
    "format:check": "prettier --check 'resources/**/*.blade.php'"
  }
}

# Pre-commit hook will work automatically!
```

### For API Projects (Express/Fastify)

```bash
# Standard Node.js setup applies
# Add OpenAPI documentation

npm install --save-dev @types/node @types/express

# Create openapi/ directory
mkdir -p openapi/schemas
```

---

## Final Verification

```bash
# Run all checks locally
npm run format:check
bash scripts/check-licenses.sh
git status  # Should be clean

# Test pre-commit hook
echo "# Test" > test.txt
git add test.txt
git commit -m "test: verify setup"
# Should see: "🔍 Pre-commit Hook: Running checks..."

# Clean up
git reset HEAD~1
rm test.txt

# Push initial commit
git add .
git commit -S -m "chore: initial repository setup"
git push origin main
```

---

## Post-Setup Checklist

- [ ] Pre-commit hook installed and tested
- [ ] Prettier configuration present
- [ ] REUSE compliance configured
- [ ] License policy file created
- [ ] All required workflows added
- [ ] Branch protection rules configured
- [ ] README.md created with org links
- [ ] Initial commit signed and pushed
- [ ] All CI checks passing

---

## Related Documentation

- [Pre-Commit Hook Installation](../.github/templates/hooks/INSTALLATION.md)
- [Lesson #15: Configuration Centralization](./LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-15-configuration-centralization)
- [Lesson #17: Git State Verification](./LESSONS-LEARNED-CONTRACTS-REPO.md#lesson-17-git-state-verification-after-work-sessions)
- [DRY Multi-Repo Strategy](./DRY-ANALYSIS-AND-STRATEGY.md)

---

## Changelog

| Date       | Change                         | Author |
| ---------- | ------------------------------ | ------ |
| 2025-10-14 | Initial repository setup guide | Agent  |

---

**Last Updated:** 2025-10-14
**Status:** Active - Use for all new SecPal repositories
