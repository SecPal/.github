#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

echo "🔧 Setting up Git hooks for all SecPal repositories..."
echo ""

# Determine workspace root (parent directory of .github)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$WORKSPACE_ROOT"

REPOS=("api" "frontend" "contracts" "android" "secpal.app" "guardguide.de" "changelog" ".github")
ROLLOUT_HINT="Run .github/scripts/install-polyscope-rollout.sh (or sync via Polyscope) to provision missing SecPal repositories."
SUCCESS_COUNT=0
FAILED_REPOS=()
MISSING_REPOS=()

# Check if pre-commit is installed
if ! command -v pre-commit &>/dev/null; then
	echo "⚠️  pre-commit is not installed."
	echo ""
	echo "Installing pre-commit via pip --user..."
	pip install --user pre-commit
	echo ""
fi

for repo in "${REPOS[@]}"; do
	if [ ! -e "$repo" ]; then
		# Missing managed repos are a soft warning, not a failure: workspaces that
		# have not yet synced the latest REPOS list (or are otherwise incomplete)
		# should still install hooks for whatever is present and exit 0.
		echo "  ⚠ Directory not found: $repo (skipping)"
		MISSING_REPOS+=("$repo")
		continue
	fi

	if [ ! -d "$repo" ]; then
		echo "  ✗ Path is not a directory: $repo"
		FAILED_REPOS+=("$repo (path is not a directory)")
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
			SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
		else
			echo "  ✗ Pre-push hook installation failed"
			FAILED_REPOS+=("$repo (pre-push)")
		fi
	else
                echo "  ✗ scripts/setup-pre-push.sh not found in $repo"
                FAILED_REPOS+=("$repo (setup-pre-push.sh missing)")
        fi

        # Setup pre-commit hook
        if [ -f "scripts/setup-pre-commit.sh" ]; then
                if ./scripts/setup-pre-commit.sh; then
                        echo "  ✓ Pre-commit hook installed"
                        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
                else
                        echo "  ✗ Pre-commit hook installation failed"
                        FAILED_REPOS+=("$repo (pre-commit)")
                fi
        else
                echo "  ✗ scripts/setup-pre-commit.sh not found in $repo"
                FAILED_REPOS+=("$repo (setup-pre-commit.sh missing)")
        fi

        # Setup commit-msg hook (strips AI attribution trailers)
        STRIP_SCRIPT="$WORKSPACE_ROOT/.github/scripts/strip-ai-trailers.sh"
        if [ -f "$STRIP_SCRIPT" ]; then
                HOOKS_DIR="$(git rev-parse --git-path hooks)"
                HOOK_PATH="$HOOKS_DIR/commit-msg"
                RELATIVE_TARGET="$(python3 -c "import os; print(os.path.relpath('$STRIP_SCRIPT', '$HOOKS_DIR'))")"
                mkdir -p "$HOOKS_DIR"
                if [ -L "$HOOK_PATH" ]; then
                        CURRENT_TARGET="$(readlink "$HOOK_PATH")"
                        if [ "$CURRENT_TARGET" != "$RELATIVE_TARGET" ]; then
                                ln -sf "$RELATIVE_TARGET" "$HOOK_PATH"
                        fi
                elif [ -f "$HOOK_PATH" ]; then
                        mv "$HOOK_PATH" "${HOOK_PATH}.backup"
                        ln -sf "$RELATIVE_TARGET" "$HOOK_PATH"
                else
                        ln -sf "$RELATIVE_TARGET" "$HOOK_PATH"
                fi
                echo "  ✓ Commit-msg hook (AI trailer stripping) installed"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
                echo "  ✗ strip-ai-trailers.sh not found at $STRIP_SCRIPT"
                FAILED_REPOS+=("$repo (commit-msg hook missing)")
        fi

        cd "$WORKSPACE_ROOT"
        echo ""
done

echo "════════════════════════════════════════"
echo "✨ Summary"
echo "════════════════════════════════════════"
echo "Successfully installed: $SUCCESS_COUNT hooks"

if command -v actionlint &>/dev/null; then
	echo "Optional workflow lint binary: actionlint found on PATH"
else
	echo "Optional workflow lint binary: actionlint not found on PATH"
	echo "  • Workflow linting still works via pre-commit hooks and CI"
	echo "  • Prefer manual runs with: pre-commit run actionlint --all-files"
	echo "  • Optional direct install: go install github.com/rhysd/actionlint/cmd/actionlint@latest"
fi

if [ ${#MISSING_REPOS[@]} -gt 0 ]; then
	echo "Skipped (missing directory): ${#MISSING_REPOS[@]} repositories"
	for missing in "${MISSING_REPOS[@]}"; do
		echo "  ⚠ $missing"
	done
	echo ""
	echo "💡 $ROLLOUT_HINT"
fi

if [ ${#FAILED_REPOS[@]} -gt 0 ]; then
	echo "Failed: ${#FAILED_REPOS[@]} repositories"
	for failed in "${FAILED_REPOS[@]}"; do
		echo "  ✗ $failed"
	done
	exit 1
fi

echo ""
echo "✅ All Git hooks have been successfully installed!"
echo ""
echo "📝 What's installed:"
echo "  • Pre-commit hooks: Formatting, linting, REUSE compliance"
echo "  • Pre-push hooks: Comprehensive quality checks (via scripts/preflight.sh)"
echo "  • Commit-msg hooks: Strip AI agent attribution trailers (Cursor, Copilot)"
echo ""
echo "💡 Usage:"
echo "  • Hooks run automatically on commit/push"
echo "  • Test manually: cd <repo> && ./scripts/preflight.sh"
echo "  • Manual workflow lint: pre-commit run actionlint --all-files"
echo "  • Bypass (emergencies only): git push --no-verify"
echo ""
