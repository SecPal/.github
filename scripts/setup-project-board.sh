#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: CC0-1.0

set -euo pipefail

echo "🚀 Setting up GitHub Project Board Integration for SecPal"
echo "=========================================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed!"
    echo "Install it from: https://cli.github.com"
    exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ You are not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is installed and authenticated"
echo ""

# Step 1: Create area labels
echo "📋 Step 1: Creating feature area labels..."
echo ""

labels=(
    "area: RBAC|0E8A16|Role-Based Access Control"
    "area: employee-mgmt|0E8A16|Employee Management"
    "area: qualifications|0E8A16|Qualifications & Certifications"
    "area: shift-planning|0E8A16|Shift Planning & Scheduling"
    "area: compliance|D93F0B|Legal & Compliance (BWR, DSGVO)"
    "area: guard-book|0E8A16|Guard Book & Incidents"
    "area: signatures|0E8A16|Digital Signatures"
    "area: works-council|0E8A16|Works Council Management"
    "area: client-portal|0E8A16|Client Portal & Self-Service"
    "area: infrastructure|6B7280|System & Infrastructure"
)

for label in "${labels[@]}"; do
    IFS='|' read -r name color description <<< "$label"

    if gh label list --repo SecPal/.github | awk '{print $1}' | grep -Fxq "$name"; then
        echo -e "${YELLOW}⚠️  Label '${name}' already exists, skipping...${NC}"
    else
        gh label create "$name" --color "$color" --description "$description" --repo SecPal/.github
        echo -e "${GREEN}✅ Created label: ${name}${NC}"
    fi
done

echo ""

# Step 2: Create status labels
echo "📋 Step 2: Creating status labels..."
echo ""

status_labels=(
    "status: backlog|FBCA04|In Ideas Backlog"
    "status: specified|0075CA|Specified in feature-requirements.md"
    "status: ready|0E8A16|Ready for Implementation"
    "core-feature|7057FF|Core platform feature (not small enhancement)"
)

for label in "${status_labels[@]}"; do
    IFS='|' read -r name color description <<< "$label"

    if gh label list --repo SecPal/.github | awk '{print $1}' | grep -Fxq "$name"; then
        echo -e "${YELLOW}⚠️  Label '${name}' already exists, skipping...${NC}"
    else
        gh label create "$name" --color "$color" --description "$description" --repo SecPal/.github
        echo -e "${GREEN}✅ Created label: ${name}${NC}"
    fi
done

echo ""
echo "✅ All labels created successfully!"
echo ""

# Step 3: Instructions for Project setup
echo "📊 Step 3: GitHub Project Setup"
echo "================================"
echo ""
echo "Next, you need to create a GitHub Project Board:"
echo ""
echo "1. Go to: https://github.com/orgs/SecPal/projects"
echo "2. Click 'New project'"
echo "3. Choose 'Board' layout"
echo "4. Name: 'SecPal Feature Roadmap'"
echo "5. Create these columns:"
echo "   - 💡 Ideas"
echo "   - 📋 Backlog"
echo "   - 🎯 Ready"
echo "   - 🚧 In Progress"
echo "   - 👀 In Review"
echo "   - ✅ Done"
echo ""
echo "6. After creating, note the project number from the URL:"
echo "   https://github.com/orgs/SecPal/projects/NUMBER"
echo ""
echo "7. Update .github/workflows/project-automation.yml:"
echo "   Replace 'project-url: https://github.com/orgs/SecPal/projects/1'"
echo "   with your actual project number"
echo ""

# Optional: Ask if user wants to create a test issue
echo ""
read -p "Would you like to create a test issue to verify the setup? (y/N) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Creating test issue..."

    gh issue create \
        --repo SecPal/.github \
        --title "[Test] Project Board Integration Test" \
        --body "This is a test issue to verify the project board automation.

**Feature Area:** Infrastructure
**Priority:** P3 (Low)
**Status:** Testing

This issue can be closed after verifying it appears on the project board." \
        --label "core-feature,area: infrastructure,priority: low"

    echo ""
    echo -e "${GREEN}✅ Test issue created!${NC}"
    echo "Check your project board to see if it was added automatically."
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Create your GitHub Project Board (see instructions above)"
echo "2. Update project-automation.yml with the project number"
echo "3. Commit and push the new templates and workflow"
echo "4. Start creating feature issues using the templates!"
echo ""
echo "Documentation: docs/project-board-integration.md"
echo ""
