#!/bin/bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: MIT

# Sync governance files from .github repository to other SecPal repositories
# Addresses Learned Lesson #3: Governance File Distribution
#
# WHY: Symlinks don't render properly on GitHub.com web interface
# SOLUTION: Copy files to maintain consistency across repositories
# AUTOMATION: This script ensures files stay in sync

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
WORKSPACE_ROOT="${1:-$(pwd)/..}"
SOURCE_REPO=".github"
TARGET_REPOS=("api" "frontend" "contracts")
GOVERNANCE_FILES=(
    "CONTRIBUTING.md"
    "SECURITY.md"
    "CODE_OF_CONDUCT.md"
    "CODEOWNERS"
    ".editorconfig"
    ".gitattributes"
)

# Mode: sync (copy files) or check (verify only)
MODE="${2:-sync}"

# Counters
synced_count=0
missing_count=0
outdated_count=0

echo -e "${BLUE}=== SecPal Governance File Sync ===${NC}"
echo "Workspace root: $WORKSPACE_ROOT"
echo "Mode: $MODE"
echo ""

# Verify source repository exists
if [[ ! -d "$WORKSPACE_ROOT/$SOURCE_REPO" ]]; then
    echo -e "${RED}❌ Source repository not found: $WORKSPACE_ROOT/$SOURCE_REPO${NC}"
    echo "Please run from SecPal workspace root or provide path as first argument:"
    echo "  $0 /path/to/SecPal"
    exit 1
fi

# Function to check if file content matches
# Args:
#   $1 (source): Path to source file
#   $2 (target): Path to target file
# Returns:
#   0 if files match exactly (including whitespace)
#   1 if target doesn't exist or files differ
files_match() {
    local source="$1"
    local target="$2"

    if [[ ! -f "$target" ]]; then
        return 1  # Target doesn't exist
    fi

    # Compare file content (exact match, including whitespace)
    if diff -q "$source" "$target" > /dev/null 2>&1; then
        return 0  # Files match
    else
        return 1  # Files differ
    fi
}

# Process each repository
for repo in "${TARGET_REPOS[@]}"; do
    repo_path="$WORKSPACE_ROOT/$repo"

    echo -e "${BLUE}Processing repository: $repo${NC}"

    # Check if repository exists
    if [[ ! -d "$repo_path" ]]; then
        echo -e "${YELLOW}⚠️  Repository not found: $repo_path (skipping)${NC}"
        echo ""
        continue
    fi

    # Process each governance file
    for file in "${GOVERNANCE_FILES[@]}"; do
        source_file="$WORKSPACE_ROOT/$SOURCE_REPO/$file"
        target_file="$repo_path/$file"

        # Check if source file exists
        if [[ ! -f "$source_file" ]]; then
            echo -e "${YELLOW}⚠️  Source file not found: $file (skipping)${NC}"
            continue
        fi

        # Check if target matches source
        if files_match "$source_file" "$target_file"; then
            echo -e "${GREEN}✅ $file (already in sync)${NC}"
            synced_count=$((synced_count + 1))
        else
            if [[ "$MODE" == "check" ]]; then
                if [[ ! -f "$target_file" ]]; then
                    echo -e "${RED}❌ $file (missing)${NC}"
                    missing_count=$((missing_count + 1))
                else
                    echo -e "${RED}❌ $file (outdated)${NC}"
                    outdated_count=$((outdated_count + 1))
                fi
            else
                # Sync mode: copy file
                # Check if target exists BEFORE copying to determine correct message
                local msg="created"
                if [[ -f "$target_file" ]]; then
                    msg="updated"
                fi

                cp "$source_file" "$target_file"
                echo -e "${GREEN}✅ $file ($msg)${NC}"
                synced_count=$((synced_count + 1))
            fi
        fi
    done

    echo ""
done

# Summary
echo -e "${BLUE}=== Summary ===${NC}"
if [[ "$MODE" == "check" ]]; then
    total_issues=$((missing_count + outdated_count))
    echo "Files in sync: $synced_count"
    echo "Missing files: $missing_count"
    echo "Outdated files: $outdated_count"
    echo ""
    if [[ $total_issues -eq 0 ]]; then
        echo -e "${GREEN}✅ All governance files are in sync across repositories${NC}"
        exit 0
    else
        echo -e "${RED}❌ Found $total_issues issue(s) that need attention${NC}"
        echo ""
        echo "Run without 'check' argument to sync files:"
        echo "  $0 $WORKSPACE_ROOT"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Synced $synced_count file(s) across ${#TARGET_REPOS[@]} repositories${NC}"
    echo ""
    echo "Don't forget to commit changes in each repository:"
    for repo in "${TARGET_REPOS[@]}"; do
        echo "  cd $WORKSPACE_ROOT/$repo && git add . && git commit -m 'chore: sync governance files from .github'"
    done
fi
