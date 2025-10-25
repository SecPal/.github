#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: AGPL-3.0-or-later

set -euo pipefail

# Sync GitHub labels from organization standards to a repository
# Usage: ./sync-labels.sh <repository-name>
# Example: ./sync-labels.sh contracts

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG="SecPal"

# Check if repository name is provided
if [ $# -eq 0 ]; then
  echo "Usage: $0 <repository-name>"
  echo "Example: $0 contracts"
  exit 1
fi

REPO="$1"

echo "🏷️  Syncing labels to SecPal/$REPO..."
echo ""

# Standard labels with descriptions and colors
# Format: "name|color|description"
declare -a LABELS=(
  # Type labels
  "bug|d73a4a|Something isn't working"
  "enhancement|a2eeef|New feature or request"
  "documentation|0075ca|Improvements or additions to documentation"
  "config-infrastructure|ededed|Configuration or infrastructure changes"
  "security|ededed|Security-related changes or vulnerabilities"
  "dependencies|0366d6|Pull requests that update a dependency file"
  "breaking-change|ededed|Changes that break backward compatibility"
  "developer-experience|ededed|Improvements to developer experience (DX)"
  "legal|ededed|Legal compliance, licensing, CLA"

  # Priority labels
  "priority: high|ededed|Needs immediate attention"
  "priority: medium|ededed|Important but not urgent"

  # Status labels
  "help wanted|008672|Extra attention is needed"
  "good first issue|7057ff|Good for newcomers"
  "discussion|ededed|Needs further discussion before implementation"
  "duplicate|cfd3d7|This issue or pull request already exists"
  "invalid|e4e669|This doesn't seem right"
  "wontfix|ffffff|This will not be worked on"
  "question|d876e3|Further information is requested"

  # Automation labels
  "dependabot|0366d6|Pull requests created by Dependabot"
  "large-pr-approved|FFA500|Approved large PR (boilerplate/templates that cannot be split)"
)

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
  echo "❌ Error: GitHub CLI (gh) is not installed"
  echo "Install: https://cli.github.com/"
  exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
  echo "❌ Error: Not authenticated with GitHub CLI"
  echo "Run: gh auth login"
  exit 1
fi

# Check if repository exists
if ! gh repo view "$ORG/$REPO" &> /dev/null; then
  echo "❌ Error: Repository $ORG/$REPO not found or no access"
  exit 1
fi

echo "✅ Repository $ORG/$REPO found"
echo ""

# Sync each label
CREATED=0
UPDATED=0
SKIPPED=0

for label_spec in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<< "$label_spec"

  # Check if label exists
  if gh label list --repo "$ORG/$REPO" --json name --jq '.[].name' | grep -q "^${name}$"; then
    # Label exists, update it
    CURRENT_COLOR=$(gh label list --repo "$ORG/$REPO" --json name,color --jq ".[] | select(.name==\"$name\") | .color")
    CURRENT_DESC=$(gh label list --repo "$ORG/$REPO" --json name,description --jq ".[] | select(.name==\"$name\") | .description")

    if [ "$CURRENT_COLOR" = "$color" ] && [ "$CURRENT_DESC" = "$description" ]; then
      # Already up to date
      ((SKIPPED++))
    else
      # Update needed
      if gh label edit "$name" --repo "$ORG/$REPO" --color "$color" --description "$description" &> /dev/null; then
        echo "🔄 Updated: $name"
        ((UPDATED++))
      else
        echo "❌ Failed to update: $name"
      fi
    fi
  else
    # Label doesn't exist, create it
    if gh label create "$name" --repo "$ORG/$REPO" --color "$color" --description "$description" &> /dev/null; then
      echo "✨ Created: $name"
      ((CREATED++))
    else
      echo "❌ Failed to create: $name"
    fi
  fi
done

echo ""
echo "📊 Summary:"
echo "   Created: $CREATED"
echo "   Updated: $UPDATED"
echo "   Skipped: $SKIPPED"
echo ""
echo "✅ Label sync complete for $ORG/$REPO"
echo ""
echo "💡 Tip: Review labels at https://github.com/$ORG/$REPO/labels"
