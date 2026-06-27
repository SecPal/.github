#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/validate-ai-instructions.sh" "$@"
