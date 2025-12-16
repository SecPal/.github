#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

echo "🔧 Setting up Git hooks for all SecPal repositories..."
echo ""

# Determine workspace root (parent directory of .github)
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$WORKSPACE_ROOT"

REPOS=("api" "frontend" "contracts" ".github")
SUCCESS_COUNT=0
FAILED_REPOS=()

# Check if pre-commit is installed
if ! command -v pre-commit &>/dev/null; then
	echo "⚠️  pre-commit is not installed."
	echo ""
	echo "Installing pre-commit via pip --user..."
	pip install --user pre-commit
	echo ""
fi

for repo in "${REPOS[@]}"; do
	if [ ! -d "$repo" ]; then
		echo "⚠️  Skipping $repo (directory not found)"
		continue
	fi

	echo "────────────────────────────────────────"
	echo "📦 Setting up hooks in $repo"
	echo "────────────────────────────────────────"
	cd "$repo"

	# Setup pre-push hook
	if [ -f "scripts/setup-pre-push.sh" ]; then
		if ./scripts/setup-pre-push.sh; then
			echo "  ✓ Pre-push hook installed"
		else
			echo "  ✗ Pre-push hook installation failed"
			FAILED_REPOS+=("$repo (pre-push)")
		fi
	else
		echo "  ⚠️  scripts/setup-pre-push.sh not found"
	fi

	# Setup pre-commit hook
	if [ -f "scripts/setup-pre-commit.sh" ]; then
		if ./scripts/setup-pre-commit.sh; then
			echo "  ✓ Pre-commit hook installed"
			((SUCCESS_COUNT++))
		else
			echo "  ✗ Pre-commit hook installation failed"
			FAILED_REPOS+=("$repo (pre-commit)")
		fi
	else
		echo "  ⚠️  scripts/setup-pre-commit.sh not found"
	fi

	cd "$WORKSPACE_ROOT"
	echo ""
done

echo "════════════════════════════════════════"
echo "✨ Summary"
echo "════════════════════════════════════════"
echo "Successfully configured: $SUCCESS_COUNT repositories"

if [ ${#FAILED_REPOS[@]} -gt 0 ]; then
	echo "Failed: ${#FAILED_REPOS[@]} repositories"
	for failed in "${FAILED_REPOS[@]}"; do
		echo "  ✗ $failed"
	done
	exit 1
else
	echo ""
	echo "✅ All Git hooks have been successfully installed!"
	echo ""
	echo "📝 What's installed:"
	echo "  • Pre-commit hooks: Formatting, linting, REUSE compliance"
	echo "  • Pre-push hooks: Comprehensive quality checks (via scripts/preflight.sh)"
	echo ""
	echo "💡 Usage:"
	echo "  • Hooks run automatically on commit/push"
	echo "  • Test manually: cd <repo> && ./scripts/preflight.sh"
	echo "  • Bypass (emergencies only): git push --no-verify"
	echo ""
fi
