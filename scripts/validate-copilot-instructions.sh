#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Retain this filename for existing callers, but keep one validation contract.
# The canonical validator owns required files, structure, licensing, Markdown,
# focused-overlay frontmatter, and the runtime discovery ceiling.
exec "$SCRIPT_DIR/validate-ai-instructions.sh" "$@"
