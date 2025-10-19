#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

# Auto-detect default branch (fallback to main)
BASE="$(git remote show origin 2>/dev/null | sed -n '/HEAD branch/s/.*: //p')"
[ -z "${BASE:-}" ] && BASE="main"
git fetch origin "$BASE" --depth=1 || true

echo "Using base branch: $BASE"

# 0) Formatting & Compliance
if command -v npx >/dev/null 2>&1; then
  npx prettier --check '**/*.{md,yml,yaml,json,ts,tsx,js,jsx}' || true  # Don't fail on format
fi
if command -v reuse >/dev/null 2>&1; then
  reuse lint
fi
if command -v npx >/dev/null 2>&1; then
  npx markdownlint-cli2 '**/*.md' || true
fi

# 1) PHP / Laravel
if [ -f composer.json ]; then
  composer install --no-interaction --no-progress --prefer-dist --optimize-autoloader
  ./vendor/bin/phpstan analyse --level=max
  php artisan test --parallel
fi

# 2) Node / React
if [ -f package.json ] || [ -f pnpm-lock.yaml ]; then
  pnpm install --frozen-lockfile
  pnpm lint
  pnpm typecheck
  pnpm test
fi

# 3) OpenAPI (Spectral)
if [ -f docs/openapi.yaml ]; then
  npx @stoplight/spectral-cli lint docs/openapi.yaml
fi

# 4) Semgrep (optional: if installed)
if command -v semgrep >/dev/null 2>&1; then
  semgrep --config p/owasp-top-ten --config p/r2c-ci --error --skip-unknown-extensions .
else
  echo "Semgrep not found – skipping security scan (optional)."
fi

# 5) Check PR size locally (against BASE)
CHANGED=$(git diff --shortstat "origin/$BASE"...HEAD 2>/dev/null | awk '{print $4+$6}')
[ -z "$CHANGED" ] && CHANGED=0
if [ "$CHANGED" -gt 600 ]; then
  echo "PR too large ($CHANGED > 600 lines). Please split into smaller slices." >&2
  exit 2
fi

echo "Preflight OK · Changed lines: $CHANGED"
