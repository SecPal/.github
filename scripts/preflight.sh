#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

# Default-Branch automatisch ermitteln (fällt zurück auf main)
BASE="$(git remote show origin 2>/dev/null | sed -n '/HEAD branch/s/.*: //p')"
[ -z "${BASE:-}" ] && BASE="main"
git fetch origin "$BASE" --depth=1 || true

echo "Using base branch: $BASE"

# 1) PHP / Laravel
composer install --no-interaction --no-progress
vendor/bin/phpstan analyse --level=max
php artisan test --parallel

# 2) Node / React
pnpm i --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test

# 3) OpenAPI (Spectral)
npx spectral lint docs/openapi.yaml

# 4) Semgrep (optional: falls installiert)
if command -v semgrep >/dev/null 2>&1; then
  semgrep ci --config p/owasp-top-ten --config p/r2c-ci --error --skip-unknown-extensions
else
  echo "Semgrep nicht gefunden – überspringe Security-Scan (optional)."
fi

# 5) PR-Size lokal prüfen (gegen BASE)
CHANGED=$(git diff --shortstat "origin/$BASE"...HEAD | awk '{print $4+$6}')
[ -z "$CHANGED" ] && CHANGED=0
if [ "$CHANGED" -gt 600 ]; then
  echo "PR zu groß ($CHANGED > 600 Zeilen). Bitte in Slices zerlegen." >&2
  exit 2
fi

echo "Preflight OK · Changed lines: $CHANGED"
