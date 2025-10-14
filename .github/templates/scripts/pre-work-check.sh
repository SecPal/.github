#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Pre-Work Checklist - Run BEFORE starting work on any branch
#
# Usage: ./scripts/pre-work-check.sh
#
# Ensures clean state and up-to-date base before starting work

set -e

echo "🚀 Pre-Work Checklist (Preventing merge conflicts)..."
echo ""

# 1. Check we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "❌ Not in a git repository!"
  exit 1
fi

# 2. Check for uncommitted changes
echo "📝 Checking for uncommitted changes..."
if ! git diff-index --quiet HEAD --; then
  echo ""
  echo "❌ You have uncommitted changes!"
  echo ""
  echo "Commit or stash them before starting new work:"
  echo "  git status"
  echo "  git add -A && git commit -m '...'"
  echo "  # OR"
  echo "  git stash"
  echo ""
  exit 1
fi
echo "✅ No uncommitted changes"
echo ""

# 3. Update main branch
echo "🔄 Updating main branch..."
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git fetch origin main --quiet

if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "  Current branch: $CURRENT_BRANCH"
  echo "  Switching to main..."
  git checkout -B main origin/main --quiet
fi

# Check if main needs update
LOCAL_COMMIT=$(git rev-parse main)
REMOTE_COMMIT=$(git rev-parse origin/main)

if [ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]; then
  echo "  Pulling latest changes..."
  git pull --ff-only origin main --quiet
  echo "✅ Main branch updated"
else
  echo "✅ Main branch already up-to-date"
fi
echo ""

# 4. Ready to create branch
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Ready to start work!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Create your feature branch:"
echo "  git checkout -b feature/your-branch-name"
echo ""
echo "Your branch will be based on the latest main ✓"
echo ""
