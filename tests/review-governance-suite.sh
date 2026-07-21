#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

for check in \
  "$SCRIPT_DIR"/validate-*-instructions.sh \
  "$SCRIPT_DIR"/*-review-memory*.sh; do
  test -x "$check"
  "$check"
done
