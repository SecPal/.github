#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

# Auto-detect default branch (fallback to main)
BASE="$(git remote show origin 2>/dev/null | sed -n '/HEAD branch/s/.*: //p')"
[ -z "${BASE:-}" ] && BASE="main"
if ! git fetch origin "$BASE" --depth=1 2>/dev/null; then
  echo "Warning: Failed to fetch origin/$BASE - PR size check may use stale data" >&2
fi

echo "Using base branch: $BASE"

# 0) Formatting & Compliance
FORMAT_EXIT=0
if command -v npx >/dev/null 2>&1; then
  npx prettier --check '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}' || FORMAT_EXIT=1
  npx markdownlint-cli2 '**/*.md' || FORMAT_EXIT=1
  # Workflow linting (part of documented gates)
  if [ -d .github/workflows ]; then
    npx actionlint || FORMAT_EXIT=1
  fi
fi
if command -v reuse >/dev/null 2>&1; then
  reuse lint || FORMAT_EXIT=1
fi
if [ "$FORMAT_EXIT" -ne 0 ]; then
  echo "Formatting/compliance checks failed. Fix issues above." >&2
  exit 1
fi

# 1) PHP / Laravel
if [ -f composer.json ]; then
  composer install --no-interaction --no-progress --prefer-dist --optimize-autoloader
  # Run Laravel Pint code style check if available (blocking: aligns with gates)
  if [ -x ./vendor/bin/pint ]; then
    ./vendor/bin/pint --test
  fi
  # Run PHPStan (use configured level from phpstan.neon if exists, else max)
  if [ -f phpstan.neon ] || [ -f phpstan.neon.dist ]; then
    ./vendor/bin/phpstan analyse
  else
    ./vendor/bin/phpstan analyse --level=max
  fi
  # Run tests (Laravel Artisan → Pest → PHPUnit)
  if [ -f artisan ]; then
    php artisan test --parallel
  elif [ -x ./vendor/bin/pest ]; then
    ./vendor/bin/pest --parallel
  elif [ -x ./vendor/bin/phpunit ]; then
    ./vendor/bin/phpunit
  fi
fi

# 2) Node / React
if [ -f pnpm-lock.yaml ] && command -v pnpm >/dev/null 2>&1; then
  pnpm install --frozen-lockfile
  pnpm lint
  pnpm typecheck
  pnpm test
elif [ -f package-lock.json ] && command -v npm >/dev/null 2>&1; then
  npm ci
  npm run lint
  npm run typecheck
  npm run test
elif [ -f yarn.lock ] && command -v yarn >/dev/null 2>&1; then
  yarn install --frozen-lockfile
  yarn lint
  yarn typecheck
  yarn test
fi

# 3) OpenAPI (Spectral)
if [ -f docs/openapi.yaml ] && command -v npx >/dev/null 2>&1; then
  npx @stoplight/spectral-cli lint docs/openapi.yaml
fi

# 4) Semgrep (optional: if installed)
if command -v semgrep >/dev/null 2>&1; then
  semgrep --config p/owasp-top-ten --config p/r2c-ci --error --skip-unknown-extensions \
    --exclude node_modules --exclude vendor --exclude .git \
    --exclude dist --exclude build --exclude coverage --exclude .next \
    .
else
  echo "Semgrep not found – skipping security scan (optional)."
fi

# 5) Check PR size locally (against BASE)
if ! git rev-parse -q --verify "origin/$BASE" >/dev/null 2>&1; then
  echo "Error: Cannot verify base branch origin/$BASE. Run 'git fetch origin $BASE' first." >&2
  exit 1
fi

MERGE_BASE=$(git merge-base "origin/$BASE" HEAD 2>/dev/null)
if [ -z "$MERGE_BASE" ]; then
  echo "Error: Cannot determine merge base with origin/$BASE." >&2
  exit 1
fi

CHANGED=$(git diff --shortstat "$MERGE_BASE"...HEAD 2>/dev/null | awk '{print $4+$6}')
[ -z "$CHANGED" ] && CHANGED=0
if [ "$CHANGED" -gt 600 ]; then
  echo "PR too large ($CHANGED > 600 lines). Please split into smaller slices." >&2
  exit 2
fi

echo "Preflight OK · Changed lines: $CHANGED"
