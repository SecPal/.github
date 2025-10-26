#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

echo "🔧 Setting up pre-push hook for SecPal..."

# Get the repository root
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Check if preflight.sh exists
if [ ! -f "scripts/preflight.sh" ]; then
	echo "❌ scripts/preflight.sh not found in repository"
	exit 1
fi

# Create the pre-push hook as a symlink
HOOK_PATH=".git/hooks/pre-push"
TARGET_PATH="../../scripts/preflight.sh"

if [ -e "$HOOK_PATH" ] && [ ! -L "$HOOK_PATH" ]; then
	echo "⚠️  Warning: .git/hooks/pre-push already exists and is not a symlink"
	echo "   Backing up to .git/hooks/pre-push.backup"
	mv "$HOOK_PATH" "$HOOK_PATH.backup"
fi

# Create the symlink
ln -sf "$TARGET_PATH" "$HOOK_PATH"

echo "✅ Pre-push hook installed successfully!"
echo ""
echo "The hook will run automatically before every push."
echo "It will execute: scripts/preflight.sh"
echo ""
echo "To bypass the hook (not recommended): git push --no-verify"
echo "To test the hook manually: ./scripts/preflight.sh"
