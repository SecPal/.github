<!--
SPDX-FileCopyrightText: 2025 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# System Requirements Check

The `check-system-requirements.sh` script validates that all required tools and dependencies for developing all SecPal repositories are installed.

## Usage

```bash
# Check all repositories
./scripts/check-system-requirements.sh

# Check only API repository
./scripts/check-system-requirements.sh --repo=api

# Check only Frontend repository
./scripts/check-system-requirements.sh --repo=frontend

# Check only Contracts repository
./scripts/check-system-requirements.sh --repo=contracts
```

## Checked Components

### 1. Global System Tools (for all repos)

**Core Tools (critical):**

- Git
- Bash
- cURL
- jq (JSON processor)

**Quality & Compliance Tools:**

- REUSE (SPDX compliance) - critical
- npx (Node Package Runner) - critical
- ShellCheck - critical
- yamllint - optional
- actionlint (GitHub Actions) - optional

**Git Configuration:**

- Git user.name - critical
- Git user.email - critical
- GPG commit signing - recommended

### 2. API Repository (Laravel + PHP + DDEV)

**PHP & Composer:**

- PHP 8.4+ - critical
- Composer 2.x - critical

**DDEV (Development Environment):**

- DDEV installed - critical for API development
- DDEV running - warning if not started

**PostgreSQL:**

- Provided via DDEV
- No local PostgreSQL installation needed

**Local Dependencies (api/vendor):**

- Pest (`vendor/bin/pest`)
- Pint (`vendor/bin/pint`)
- PHPStan (`vendor/bin/phpstan`)

### 3. Frontend Repository (React + TypeScript + Node)

**Node.js & Package Managers:**

- Node.js 22.x+ - critical
- npm - critical
- yarn - optional
- pnpm - optional

**Local Dependencies (frontend/node_modules):**

- TypeScript
- Vite
- Vitest
- ESLint

### 4. Contracts Repository (OpenAPI)

**Node.js & npm:**

- Node.js 22.x+ - critical
- npm - critical

**Local Dependencies (contracts/node_modules):**

- @redocly/cli

### 5. Optional but Recommended

- GitHub CLI (`gh`)
- pre-commit framework
- Docker (for DDEV)
- Docker Compose (for DDEV)

## Exit Codes

- `0` - All critical requirements met
- `1` - One or more critical requirements missing

## Common Scenarios

### After Backup Restoration

After a backup restore, programs may be missing:

```bash
./scripts/check-system-requirements.sh
```

The script shows all missing tools with installation hints.

### Setting Up a New Development System

For a completely new system:

```bash
# 1. Check global tools
./scripts/check-system-requirements.sh

# 2. Install missing tools (follow hints from script)

# 3. Install repository-specific dependencies
cd ../api && composer install && ddev start
cd ../frontend && npm install
cd ../contracts && npm install

# 4. Check again
cd ../.github && ./scripts/check-system-requirements.sh
```

### CI/CD Integration

The script can be used in CI pipelines:

```yaml
- name: Check system requirements
  run: ./scripts/check-system-requirements.sh
```

## Special Considerations

### DDEV in API Repository

The API repository uses **DDEV** as development environment. This is an important distinction:

- DDEV manages PHP, PostgreSQL and other services
- All Laravel commands must be executed via `ddev exec`
- Example: `ddev exec php artisan test`

### Multi-Repo Structure

SecPal is **not a monorepo**, but consists of multiple independent repositories:

- `api/` - Laravel Backend
- `frontend/` - React Frontend
- `contracts/` - OpenAPI Specifications
- `.github/` - Organization-wide Configuration

Each repository has its own dependencies and quality gates.

## Troubleshooting

### "vendor/ directory not found"

```bash
cd ../api
composer install
# or with DDEV:
ddev composer install
```

### "node_modules/ directory not found"

```bash
cd ../frontend  # or ../contracts
npm install
```

### "DDEV is installed but not running"

```bash
cd ../api
ddev start
```

### "GPG commit signing not configured"

```bash
git config --global commit.gpgsign true
git config --global user.signingkey <your-gpg-key-id>
```

## Future Enhancements

The script can be extended with:

- Version checks for local dependencies (not just existence)
- Docker/Docker Compose version checking
- Disk space checks
- Memory requirements
- VS Code extensions (if VS Code is detected)

## See Also

- [API DEVELOPMENT.md](https://github.com/SecPal/api/blob/main/DEVELOPMENT.md) - API Development Setup
- [Frontend README.md](https://github.com/SecPal/frontend/blob/main/README.md) - Frontend Setup
- [Contracts README.md](https://github.com/SecPal/contracts/blob/main/README.md) - Contracts Setup
- [Preflight Scripts](../scripts/preflight.sh) - Quality Gate Checks
