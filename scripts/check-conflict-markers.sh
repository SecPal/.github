#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: MIT

# ============================================================================
# Git Conflict Marker Detection
# ============================================================================
# Detects unresolved Git merge conflict markers in tracked files to prevent
# accidental commits of broken code.
#
# Exit codes:
#   0 - No conflict markers found
#   1 - Conflict markers detected
# ============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Conflict marker patterns
MARKERS=(
  "<<<<<<< "  # Start of conflict (from HEAD)
  "======="   # Separator between changes
  ">>>>>>> "  # End of conflict (from incoming)
  "||||||"    # Optional: diff3 style marker
)

CONFLICTS_FOUND=0
CHECKED_FILES=0

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Git Conflict Marker Detection${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Get list of tracked files (excluding .git directory)
while IFS= read -r -d '' file; do
  # Skip binary files and non-text files
  if file "$file" | grep -q "text"; then
    CHECKED_FILES=$((CHECKED_FILES + 1))

    # Check each conflict marker pattern
    for marker in "${MARKERS[@]}"; do
      if grep -n "^${marker}" "$file" > /dev/null 2>&1; then
        if [ $CONFLICTS_FOUND -eq 0 ]; then
          echo -e "${RED}✗ Conflict markers detected:${NC}"
          echo ""
        fi

        CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
        echo -e "${YELLOW}File:${NC} $file"

        # Show lines with conflict markers
        grep -n "^${marker}" "$file" | while IFS=: read -r line_num line_content; do
          echo -e "  ${RED}Line $line_num:${NC} ${line_content:0:60}..."
        done
        echo ""
        break  # Only report once per file
      fi
    done
  fi
done < <(git ls-files -z)

echo -e "${BLUE}─────────────────────────────────────────────────────${NC}"
echo -e "Checked files: ${CHECKED_FILES}"

if [ $CONFLICTS_FOUND -eq 0 ]; then
  echo -e "${GREEN}✓ No conflict markers found${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "${RED}✗ Found conflict markers in files${NC}"
  echo ""
  echo -e "${YELLOW}Action required:${NC}"
  echo "1. Open the affected files"
  echo "2. Search for conflict markers: <<<<<<<, =======, >>>>>>>"
  echo "3. Manually resolve the conflicts"
  echo "4. Remove all conflict markers"
  echo "5. Test your changes"
  echo "6. Commit again"
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  exit 1
fi
