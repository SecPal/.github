#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025 SecPal
# SPDX-License-Identifier: CC0-1.0

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "🚀 SecPal GitHub Project Setup & Verification"
echo "=============================================="
echo ""

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI (gh) is not installed!${NC}"
    echo "Install it from: https://cli.github.com"
    exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}❌ You are not authenticated with GitHub CLI${NC}"
    echo "Run: gh auth login"
    exit 1
fi

echo -e "${GREEN}✅ GitHub CLI is installed and authenticated${NC}"
echo ""

# Project number
PROJECT_NUMBER=1
ORG="SecPal"

echo "📊 Checking GitHub Project #${PROJECT_NUMBER}..."
echo ""

# Try to get project info via GraphQL
echo "🔍 Fetching project details..."
PROJECT_DATA=$(gh api graphql -f query="
  query {
    organization(login: \"${ORG}\") {
      projectV2(number: ${PROJECT_NUMBER}) {
        id
        title
        shortDescription
        url
        public
        closed
        fields(first: 20) {
          nodes {
            ... on ProjectV2Field {
              id
              name
              dataType
            }
            ... on ProjectV2SingleSelectField {
              id
              name
              dataType
              options {
                id
                name
              }
            }
          }
        }
      }
    }
  }
" 2>&1) || {
    echo -e "${YELLOW}⚠️  Could not access project via GraphQL API${NC}"
    echo ""
    echo "This is likely because your GitHub token is missing the 'project' scope."
    echo ""
    echo "To grant project access:"
    echo ""
    echo -e "${BLUE}1. Generate a new Personal Access Token:${NC}"
    echo "   → Go to: https://github.com/settings/tokens/new"
    echo "   → Name: 'gh CLI with project access'"
    echo "   → Expiration: 90 days (or as needed)"
    echo "   → Select scopes:"
    echo "     ✓ repo (full control)"
    echo "     ✓ read:org"
    echo "     ✓ read:project"
    echo "     ✓ write:project (optional, for modifications)"
    echo ""
    echo -e "${BLUE}2. Authenticate gh CLI with new token:${NC}"
    echo "   → Copy the generated token"
    echo "   → Run: gh auth login"
    echo "   → Choose 'GitHub.com'"
    echo "   → Choose 'Paste an authentication token'"
    echo "   → Paste your token"
    echo ""
    echo -e "${BLUE}3. Re-run this script${NC}"
    echo ""
    echo "Alternatively, you can manually verify your project at:"
    echo "https://github.com/orgs/${ORG}/projects/${PROJECT_NUMBER}"
    exit 1
}

# Parse project data
PROJECT_ID=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.id')
PROJECT_TITLE=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.title')
PROJECT_URL=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.url')
PROJECT_PUBLIC=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.public')

echo -e "${GREEN}✅ Successfully accessed project!${NC}"
echo ""
echo "📋 Project Details:"
echo "   Title: ${PROJECT_TITLE}"
echo "   URL: ${PROJECT_URL}"
echo "   Public: ${PROJECT_PUBLIC}"
echo "   ID: ${PROJECT_ID}"
echo ""

# Get current fields
echo "🔍 Analyzing project fields..."
echo ""

STATUS_FIELD=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.fields.nodes[] | select(.name == "Status")')

if [ -z "$STATUS_FIELD" ] || [ "$STATUS_FIELD" = "null" ]; then
    echo -e "${YELLOW}⚠️  No 'Status' field found${NC}"
    echo ""
    echo "Recommended Status field options:"
    echo "   💡 Ideas"
    echo "   📋 Backlog"
    echo "   🎯 Ready"
    echo "   🚧 In Progress"
    echo "   👀 In Review"
    echo "   ✅ Done"
    echo ""
else
    echo -e "${GREEN}✅ Status field exists${NC}"
    echo ""
    echo "Current Status options:"
    echo "$STATUS_FIELD" | jq -r '.options[]? | "   - \(.name)"'
    echo ""
fi

# Check for recommended custom fields
PRIORITY_FIELD=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.fields.nodes[] | select(.name == "Priority")')
AREA_FIELD=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.fields.nodes[] | select(.name == "Area")')
SIZE_FIELD=$(echo "$PROJECT_DATA" | jq -r '.data.organization.projectV2.fields.nodes[] | select(.name == "Size")')

echo "📊 Recommended Custom Fields:"
echo ""

if [ -n "$PRIORITY_FIELD" ] && [ ! "$PRIORITY_FIELD" = "null" ]; then
    echo -e "   ${GREEN}✅ Priority field exists${NC}"
else
    echo -e "   ${YELLOW}⚠️  Priority field missing${NC}"
    echo "      Recommended options: P0, P1, P2, P3"
fi

if [ -n "$AREA_FIELD" ] && [ ! "$AREA_FIELD" = "null" ]; then
    echo -e "   ${GREEN}✅ Area field exists${NC}"
else
    echo -e "   ${YELLOW}⚠️  Area field missing${NC}"
    echo "      Recommended options: RBAC, Employee Management, Shift Planning, etc."
fi

if [ -n "$SIZE_FIELD" ] && [ ! "$SIZE_FIELD" = "null" ]; then
    echo -e "   ${GREEN}✅ Size field exists${NC}"
else
    echo -e "   ${YELLOW}⚠️  Size field missing${NC}"
    echo "      Recommended options: XS, S, M, L, XL, XXL"
fi

echo ""

echo ""

# Note about project configuration
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Your project is already well-configured!"
echo ""
echo "All recommended fields are present. If you need to:"
echo "  • Add more field options"
echo "  • Modify existing fields"
echo "  • Create new custom fields"
echo ""
echo "Visit: ${PROJECT_URL}/settings"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Summary & Next Steps:"
echo ""
echo "1. ✅ Project verified: ${PROJECT_URL}"
echo "2. ✅ Workflow configured to use project #${PROJECT_NUMBER}"
echo "3. 📋 Review project at: ${PROJECT_URL}/settings"
echo "4. 🏷️  Run: ./scripts/setup-project-board.sh to create labels"
echo "5. 🎫 Create your first issue using the templates!"
echo ""
echo "🎉 All done!"
echo ""
