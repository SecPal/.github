#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Post-Commit Verification Checklist
#
# Usage: Run this after EVERY commit to ensure Lesson #17 compliance
#   ./scripts/post-commit-check.sh
#
# This enforces the documented workflow from LESSONS-LEARNED-CONTRACTS-REPO.md

set -e

echo "🔍 Post-Commit Verification (Lesson #17 compliance)..."
echo ""

# 1. Check for uncommitted changes
echo "📝 Checking for uncommitted changes..."
if ! git diff-index --quiet HEAD --; then
  echo ""
  echo "❌ UNCOMMITTED CHANGES DETECTED!"
  echo ""
  echo "Modified files:"
  git diff --name-only
  echo ""
  echo "This violates Lesson #17 (Git State Verification)"
  echo ""
  echo "Action required:"
  echo "  git add <files>"
  echo "  git commit -m '...'"
  echo ""
  exit 1
fi
echo "✅ No uncommitted changes"
echo ""

# 2. Check for untracked files (excluding allowed patterns)
echo "📂 Checking for untracked files..."
UNTRACKED=$(git ls-files --others --exclude-standard)
if [ -n "$UNTRACKED" ]; then
  echo ""
  echo "⚠️  UNTRACKED FILES DETECTED!"
  echo ""
  echo "$UNTRACKED"
  echo ""
  echo "Action required:"
  echo "  - Add to .gitignore if intentional"
  echo "  - git add <file> if should be tracked"
  echo "  - rm <file> if temporary (cleanup!)"
  echo ""
  exit 1
fi
echo "✅ No untracked files"
echo ""

# 3. Check for unstaged changes
echo "🔎 Checking for unstaged changes..."
if ! git diff --quiet; then
  echo ""
  echo "❌ UNSTAGED CHANGES DETECTED!"
  echo ""
  echo "Modified files:"
  git diff --name-only
  echo ""
  echo "This might be from formatters running after git add"
  echo ""
  echo "Action required:"
  echo "  git diff  # Review changes"
  echo "  git add -A  # Stage them"
  echo "  git commit --amend  # Or new commit"
  echo ""
  exit 1
fi
echo "✅ No unstaged changes"
echo ""

# 4. Verify current branch is synced with remote
echo "🌐 Checking branch sync status..."
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "main" ]; then
  echo "⚠️  You're on main - consider working on feature branches"
fi

# Check if branch has remote tracking
if git rev-parse --abbrev-ref --symbolic-full-name @{u} > /dev/null 2>&1; then
  REMOTE_BRANCH=$(git rev-parse --abbrev-ref --symbolic-full-name @{u})
  LOCAL_COMMIT=$(git rev-parse @)
  REMOTE_COMMIT=$(git rev-parse @{u})
  BASE_COMMIT=$(git merge-base @ @{u})

  if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo "✅ Branch is synced with $REMOTE_BRANCH"
  elif [ "$LOCAL_COMMIT" = "$BASE_COMMIT" ]; then
    echo "⚠️  Branch is behind $REMOTE_BRANCH - need to pull"
  elif [ "$REMOTE_COMMIT" = "$BASE_COMMIT" ]; then
    echo "⚠️  Branch is ahead of $REMOTE_BRANCH - need to push"
  else
    echo "⚠️  Branch has diverged from $REMOTE_BRANCH - need to sync"
  fi
else
  echo "ℹ️  Branch has no remote tracking branch yet"
fi
echo ""

# 5. Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Lesson #17 Compliance: PASSED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Working directory is clean!"
echo "Safe to continue working or push."
echo ""
