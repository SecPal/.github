#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
# SPDX-License-Identifier: MIT

# ============================================================================
# SecPal System Requirements Check
# ============================================================================
# Validates that all required tools and dependencies are installed for
# development across all SecPal repositories (api, frontend, contracts, android).
#
# Usage:
#   ./scripts/check-system-requirements.sh [--repo=<name>]
#
# Options:
#   --repo=api        Check only API repository requirements
#   --repo=frontend   Check only Frontend repository requirements
#   --repo=contracts  Check only Contracts repository requirements
#   --repo=android    Check only Android repository requirements
#   (no option)       Check all repositories
#
# Exit codes:
#   0 - All critical requirements met
#   1 - One or more critical requirements missing
# ============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CRITICAL_MISSING=0
WARNING_COUNT=0
OK_COUNT=0

# Track Node.js check to avoid duplicates
NODE_CHECKED=false

# Repository filter
REPO_FILTER=""
if [[ "${1:-}" =~ --repo=(.*) ]]; then
  REPO_FILTER="${BASH_REMATCH[1]}"
fi

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
}

print_section() {
  echo ""
  echo -e "${BLUE}─── $1 ───${NC}"
}

increment_warning() {
  WARNING_COUNT=$((WARNING_COUNT + 1))
}

increment_critical_missing() {
  CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
}

resolve_java_tool() {
  local tool_name="$1"

  if [ -n "${JAVA_HOME:-}" ] && [ -x "${JAVA_HOME%/}/bin/$tool_name" ]; then
    printf '%s\n' "${JAVA_HOME%/}/bin/$tool_name"
    return 0
  fi

  if command -v "$tool_name" >/dev/null 2>&1; then
    command -v "$tool_name"
    return 0
  fi

  return 1
}

check_command() {
  local cmd=$1
  local name=$2
  local severity=${3:-critical}
  local install_hint=${4:-}

  if command -v "$cmd" >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} $name"
    OK_COUNT=$((OK_COUNT + 1))
    return 0
  else
    if [ "$severity" = "critical" ]; then
      echo -e "${RED}✗${NC} $name ${RED}(REQUIRED)${NC}"
      [ -n "$install_hint" ] && echo -e "  ${YELLOW}→${NC} $install_hint"
      increment_critical_missing
      return 0
    else
      echo -e "${YELLOW}⚠${NC} $name ${YELLOW}(optional but recommended)${NC}"
      [ -n "$install_hint" ] && echo -e "  ${YELLOW}→${NC} $install_hint"
      increment_warning
      return 0  # Don't stop script for optional tools
    fi
  fi
}

check_android_dependency() {
  local package_name="$1"
  local display_name="$2"

  if npm list "$package_name" --silent >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} $display_name installed"
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo -e "${RED}✗${NC} $display_name not installed"
    increment_critical_missing
  fi
}

# ============================================================================
# Main Checks
# ============================================================================

print_header "SecPal System Requirements Check"

if [ -n "$REPO_FILTER" ]; then
  echo -e "${BLUE}ℹ${NC} Checking requirements for: ${YELLOW}$REPO_FILTER${NC} repository only"
else
  echo -e "${BLUE}ℹ${NC} Checking requirements for: ${YELLOW}all${NC} repositories"
fi

# ============================================================================
# 1. Global System Tools (required by all repos)
# ============================================================================

print_header "1. Global System Tools"

print_section "Core Tools"
check_command "git" "Git" "critical" "Install via package manager"
check_command "bash" "Bash" "critical"
check_command "curl" "cURL" "critical"
check_command "jq" "jq (JSON processor)" "critical" "Install: sudo apt install jq / brew install jq"

print_section "Quality & Compliance Tools"
check_command "reuse" "REUSE (SPDX compliance)" "critical" "Install: pip3 install reuse"
check_command "npx" "npx (Node Package Runner)" "critical" "Comes with npm (install Node.js)"

# Helper function to check npx-based tools (DRY principle)
check_npx_tool() {
  local tool_name="$1"
  local package_name="${2:-$tool_name}"
  local executable_name="${3:-$tool_name}"
  if command -v npx >/dev/null 2>&1; then
    if npx --yes --package "$package_name" "$executable_name" --version >/dev/null 2>&1; then
      echo -e "${GREEN}✓${NC} $tool_name (via npx)"
      OK_COUNT=$((OK_COUNT + 1))
    else
      echo -e "${RED}✗${NC} $tool_name ${RED}(REQUIRED)${NC}"
      echo -e "  ${YELLOW}→${NC} Should be available via npx. Check npm/node installation."
      CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    fi
  else
    echo -e "${RED}✗${NC} $tool_name ${RED}(REQUIRED - npx not found)${NC}"
    CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
  fi
}

check_npx_tool "markdownlint-cli" "markdownlint-cli" "markdownlint"
check_npx_tool "prettier"

check_command "shellcheck" "ShellCheck" "critical" "Install: sudo apt install shellcheck / brew install shellcheck"
check_command "yamllint" "yamllint" "optional" "Install: pip3 install yamllint"
check_command "actionlint" "actionlint (GitHub Actions)" "optional" "Install: go install github.com/rhysd/actionlint/cmd/actionlint@latest, brew install actionlint, or place a release binary on PATH"

print_section "Git Configuration"

# Check user name and email
if git config --get user.name >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Git user.name configured"
  OK_COUNT=$((OK_COUNT + 1))
else
  echo -e "${RED}✗${NC} Git user.name not configured"
  echo -e "  ${YELLOW}→${NC} Set: git config --global user.name 'Your Name'"
  CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
fi

if git config --get user.email >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Git user.email configured"
  OK_COUNT=$((OK_COUNT + 1))
else
  echo -e "${RED}✗${NC} Git user.email not configured"
  echo -e "  ${YELLOW}→${NC} Set: git config --global user.email 'your@email.com'"
  CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
fi

# Check commit signing
if git config --get commit.gpgsign >/dev/null 2>&1; then
  gpgsign=$(git config --get commit.gpgsign)
  if [ "$gpgsign" = "true" ]; then
    echo -e "${GREEN}✓${NC} GPG commit signing enabled"
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo -e "${YELLOW}⚠${NC} GPG commit signing disabled ${YELLOW}(required)${NC}"
    echo -e "  ${YELLOW}→${NC} Enable: git config --global commit.gpgsign true"
    WARNING_COUNT=$((WARNING_COUNT + 1))
  fi
else
  echo -e "${YELLOW}⚠${NC} GPG commit signing not configured ${YELLOW}(required)${NC}"
  echo -e "  ${YELLOW}→${NC} Enable: git config --global commit.gpgsign true"
  WARNING_COUNT=$((WARNING_COUNT + 1))
fi

# ============================================================================
# 2. API Repository Requirements (Laravel + Native PHP Runtime)
# ============================================================================

if [ -z "$REPO_FILTER" ] || [ "$REPO_FILTER" = "api" ]; then
  print_header "2. API Repository (Laravel + Native PHP Runtime)"

  print_section "PHP & Composer"

  # Check PHP version
  if command -v php >/dev/null 2>&1; then
    php_version=$(php -r "echo PHP_VERSION;")
    major_minor=$(echo "$php_version" | cut -d. -f1,2)

    if awk "BEGIN {exit !($major_minor >= 8.4)}"; then
      echo -e "${GREEN}✓${NC} PHP $php_version (>= 8.4 required)"
      OK_COUNT=$((OK_COUNT + 1))
    else
      echo -e "${RED}✗${NC} PHP $php_version ${RED}(>= 8.4 required)${NC}"
      echo -e "  ${YELLOW}→${NC} Update PHP to 8.4 or higher"
      CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    fi
  else
    echo -e "${RED}✗${NC} PHP ${RED}(not found)${NC}"
    CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
  fi

  check_command "composer" "Composer" "critical" "Install: https://getcomposer.org/download/"

  print_section "Runtime Access"
  echo -e "${BLUE}ℹ${NC} API workflows use direct php artisan/composer commands"
  echo -e "${BLUE}ℹ${NC} Use a local shell or an SSH session for the target VPS runtime"

  print_section "PostgreSQL Access"
  echo -e "${BLUE}ℹ${NC} PostgreSQL is provided by the target environment or remote service"
  echo -e "${BLUE}ℹ${NC} No local PostgreSQL installation needed when using the VPS workflow"

  # Check API local dependencies
  if [ -d "../api" ]; then
    print_section "API Repository - Local Dependencies"

    if pushd "../api" >/dev/null 2>&1; then
      if [ -d "vendor" ]; then
        echo -e "${GREEN}✓${NC} vendor/ directory exists"
        OK_COUNT=$((OK_COUNT + 1))

        if [ -x "vendor/bin/pest" ]; then
          echo -e "${GREEN}✓${NC} Pest installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} Pest not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi

        if [ -x "vendor/bin/pint" ]; then
          echo -e "${GREEN}✓${NC} Pint installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} Pint not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi

        if [ -x "vendor/bin/phpstan" ]; then
          echo -e "${GREEN}✓${NC} PHPStan installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} PHPStan not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi
      else
        echo -e "${YELLOW}⚠${NC} vendor/ directory not found"
        echo -e "  ${YELLOW}→${NC} Run: composer install"
        WARNING_COUNT=$((WARNING_COUNT + 1))
      fi

      popd >/dev/null 2>&1
    else
      echo -e "${YELLOW}⚠${NC} Cannot access ../api directory"
      WARNING_COUNT=$((WARNING_COUNT + 1))
    fi
  fi
fi

# ============================================================================
# 3. Frontend Repository Requirements (React + TypeScript + Node)
# ============================================================================

if [ -z "$REPO_FILTER" ] || [ "$REPO_FILTER" = "frontend" ]; then
  print_header "3. Frontend Repository (React + TypeScript + Node)"

  print_section "Node.js & Package Managers"

  # Check Node version
  if command -v node >/dev/null 2>&1; then
    node_version=$(node --version | sed 's/v//')
    major_version=$(echo "$node_version" | cut -d. -f1)

    if [ "$major_version" -ge 22 ]; then
      echo -e "${GREEN}✓${NC} Node.js v$node_version (>= 22.x required)"
      OK_COUNT=$((OK_COUNT + 1))
    else
      echo -e "${YELLOW}⚠${NC} Node.js v$node_version ${YELLOW}(>= 22.x recommended)${NC}"
      echo -e "  ${YELLOW}→${NC} Update Node.js to 22.x LTS"
      WARNING_COUNT=$((WARNING_COUNT + 1))
    fi
    NODE_CHECKED=true
  else
    echo -e "${RED}✗${NC} Node.js ${RED}(not found)${NC}"
    CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    NODE_CHECKED=true
  fi

  check_command "npm" "npm" "critical" "Comes with Node.js"
  check_command "yarn" "yarn" "optional" "Install: npm install -g yarn"
  check_command "pnpm" "pnpm" "optional" "Install: npm install -g pnpm"

  # Check frontend local dependencies
  if [ -d "../frontend" ]; then
    print_section "Frontend Repository - Local Dependencies"

    if pushd "../frontend" >/dev/null 2>&1; then
      if [ -d "node_modules" ]; then
        echo -e "${GREEN}✓${NC} node_modules/ directory exists"
        OK_COUNT=$((OK_COUNT + 1))

        if npm list typescript --silent >/dev/null 2>&1; then
          echo -e "${GREEN}✓${NC} TypeScript installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} TypeScript not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi

        if npm list vite --silent >/dev/null 2>&1; then
          echo -e "${GREEN}✓${NC} Vite installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} Vite not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi

        if npm list vitest --silent >/dev/null 2>&1; then
          echo -e "${GREEN}✓${NC} Vitest installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} Vitest not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi

        if npm list eslint --silent >/dev/null 2>&1; then
          echo -e "${GREEN}✓${NC} ESLint installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} ESLint not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi
      else
        echo -e "${YELLOW}⚠${NC} node_modules/ directory not found"
        echo -e "  ${YELLOW}→${NC} Run: npm install"
        WARNING_COUNT=$((WARNING_COUNT + 1))
      fi

      popd >/dev/null 2>&1
    else
      echo -e "${YELLOW}⚠${NC} Cannot access ../frontend directory"
      WARNING_COUNT=$((WARNING_COUNT + 1))
    fi
  fi
fi

# ============================================================================
# 4. Contracts Repository Requirements (OpenAPI)
# ============================================================================

if [ -z "$REPO_FILTER" ] || [ "$REPO_FILTER" = "contracts" ]; then
  print_header "4. Contracts Repository (OpenAPI)"

  print_section "Node.js & npm"

  # Check Node version (skip if already checked in frontend section)
  if [ "$NODE_CHECKED" = false ]; then
    if command -v node >/dev/null 2>&1; then
      node_version=$(node --version | sed 's/v//')
      major_version=$(echo "$node_version" | cut -d. -f1)

      if [ "$major_version" -ge 22 ]; then
        echo -e "${GREEN}✓${NC} Node.js v$node_version (>= 22.x required)"
        OK_COUNT=$((OK_COUNT + 1))
      else
        echo -e "${YELLOW}⚠${NC} Node.js v$node_version ${YELLOW}(>= 22.x recommended)${NC}"
        echo -e "  ${YELLOW}→${NC} Update Node.js to 22.x LTS"
        WARNING_COUNT=$((WARNING_COUNT + 1))
      fi
    else
      echo -e "${RED}✗${NC} Node.js ${RED}(not found)${NC}"
      CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    fi

    check_command "npm" "npm" "critical" "Comes with Node.js"
  fi

  # Check contracts local dependencies
  if [ -d "../contracts" ]; then
    print_section "Contracts Repository - Local Dependencies"

    if pushd "../contracts" >/dev/null 2>&1; then
      if [ -d "node_modules" ]; then
        echo -e "${GREEN}✓${NC} node_modules/ directory exists"
        OK_COUNT=$((OK_COUNT + 1))

        if npm list @redocly/cli --silent >/dev/null 2>&1; then
          echo -e "${GREEN}✓${NC} @redocly/cli installed"
          OK_COUNT=$((OK_COUNT + 1))
        else
          echo -e "${RED}✗${NC} @redocly/cli not installed"
          CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
        fi
      else
        echo -e "${YELLOW}⚠${NC} node_modules/ directory not found"
        echo -e "  ${YELLOW}→${NC} Run: npm install"
        WARNING_COUNT=$((WARNING_COUNT + 1))
      fi

      popd >/dev/null 2>&1
    else
      echo -e "${YELLOW}⚠${NC} Cannot access ../contracts directory"
      WARNING_COUNT=$((WARNING_COUNT + 1))
    fi
  fi
fi

# ============================================================================
# 5. Android Repository Requirements (Capacitor + Native Android Toolchain)
# ============================================================================

if [ -z "$REPO_FILTER" ] || [ "$REPO_FILTER" = "android" ]; then
  print_header "5. Android Repository (Capacitor + Native Android Toolchain)"

  print_section "Node.js & npm"

  if [ "$NODE_CHECKED" = false ]; then
    if command -v node >/dev/null 2>&1; then
      node_version=$(node --version | sed 's/v//')
      major_version=$(echo "$node_version" | cut -d. -f1)

      if [ "$major_version" -ge 22 ]; then
        echo -e "${GREEN}✓${NC} Node.js v$node_version (>= 22.x required)"
        OK_COUNT=$((OK_COUNT + 1))
      else
        echo -e "${RED}✗${NC} Node.js v$node_version ${RED}(>= 22.x required)${NC}"
        echo -e "  ${YELLOW}→${NC} Update Node.js to 22.x LTS"
        CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
      fi
    else
      echo -e "${RED}✗${NC} Node.js ${RED}(not found)${NC}"
      CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    fi

    check_command "npm" "npm" "critical" "Comes with Node.js"
    NODE_CHECKED=true
  elif command -v node >/dev/null 2>&1; then
    node_version=$(node --version | sed 's/v//')
    major_version=$(echo "$node_version" | cut -d. -f1)

    if [ "$major_version" -lt 22 ]; then
      echo -e "${RED}✗${NC} Node.js v$node_version ${RED}(>= 22.x required)${NC}"
      echo -e "  ${YELLOW}→${NC} Update Node.js to 22.x LTS"
      increment_critical_missing
    fi
  fi

  print_section "Java & Android SDK"

  java_bin="$(resolve_java_tool java || true)"
  javac_bin="$(resolve_java_tool javac || true)"

  if [ -n "$java_bin" ]; then
    java_version_output="$("$java_bin" -version 2>&1 | head -n 1)"
    if printf '%s' "$java_version_output" | grep -Eq '"21(\.|")'; then
      echo -e "${GREEN}✓${NC} Java 21"
      OK_COUNT=$((OK_COUNT + 1))
    else
      echo -e "${RED}✗${NC} Java 21 ${RED}(required)${NC}"
      echo -e "  ${YELLOW}→${NC} Install Java 21 and export JAVA_HOME if needed"
      CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
    fi
  else
    echo -e "${RED}✗${NC} Java runtime ${RED}(required)${NC}"
    echo -e "  ${YELLOW}→${NC} Install Java 21 and export JAVA_HOME if needed"
    CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
  fi

  if [ -n "$javac_bin" ]; then
    echo -e "${GREEN}✓${NC} Java compiler (javac)"
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo -e "${RED}✗${NC} Java compiler (javac) ${RED}(REQUIRED)${NC}"
    echo -e "  ${YELLOW}→${NC} Install the Java 21 development package (for example openjdk-21-jdk or java-21-openjdk-devel)"
    increment_critical_missing
  fi
  check_command "sdkmanager" "Android SDK Command-Line Tools (sdkmanager)" "critical" "Install the Android command-line tools and place them under \$HOME/Android/Sdk/cmdline-tools/latest"
  check_command "adb" "Android SDK Platform-Tools (adb)" "critical" "Install Android platform-tools so debug builds and device validation can use adb"

  android_sdk_dir="${POLYSCOPE_ANDROID_SDK_ROOT:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}}"
  if [ -d "$android_sdk_dir" ] \
    && [ -d "$android_sdk_dir/platform-tools" ] \
    && [ -d "$android_sdk_dir/cmdline-tools/latest" ]; then
    echo -e "${GREEN}✓${NC} Android SDK directory exists ($android_sdk_dir)"
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo -e "${RED}✗${NC} Android SDK directory ${RED}(incomplete or not found)${NC}"
    echo -e "  ${YELLOW}→${NC} Install the Android SDK under $android_sdk_dir with platform-tools and cmdline-tools/latest, or export POLYSCOPE_ANDROID_SDK_ROOT/ANDROID_SDK_ROOT/ANDROID_HOME"
    CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
  fi

  if [ -d "../android" ]; then
    print_section "Android Repository - Local Dependencies"

    if pushd "../android" >/dev/null 2>&1; then
      if [ -d "node_modules" ]; then
        echo -e "${GREEN}✓${NC} node_modules/ directory exists"
        OK_COUNT=$((OK_COUNT + 1))
        check_android_dependency "typescript" "TypeScript"
        check_android_dependency "vite" "Vite"
        check_android_dependency "vitest" "Vitest"
        check_android_dependency "eslint" "ESLint"
      else
        echo -e "${YELLOW}⚠${NC} node_modules/ directory not found"
        echo -e "  ${YELLOW}→${NC} Run: npm install"
        WARNING_COUNT=$((WARNING_COUNT + 1))
      fi

      if [ -d "android" ]; then
        echo -e "${GREEN}✓${NC} Native Android project directory exists"
        OK_COUNT=$((OK_COUNT + 1))
      else
        echo -e "${RED}✗${NC} Native Android project directory missing"
        echo -e "  ${YELLOW}→${NC} Run: npm run cap:add:android"
        CRITICAL_MISSING=$((CRITICAL_MISSING + 1))
      fi

      popd >/dev/null 2>&1
    else
      echo -e "${YELLOW}⚠${NC} Cannot access ../android directory"
      WARNING_COUNT=$((WARNING_COUNT + 1))
    fi
  fi
fi

# ============================================================================
# 6. Optional but Recommended Tools
# ============================================================================

print_header "6. Optional but Recommended Tools"

check_command "gh" "GitHub CLI" "optional" "Install: https://cli.github.com/"
check_command "pre-commit" "pre-commit framework" "optional" "Install: pip3 install pre-commit"
check_command "ssh" "OpenSSH client" "optional" "Needed for remote API runtime access"

# ============================================================================
# Summary
# ============================================================================

print_header "Summary"

echo ""
echo -e "${GREEN}✓${NC} OK:       $OK_COUNT checks passed"
echo -e "${YELLOW}⚠${NC} Warnings: $WARNING_COUNT (optional tools missing)"
echo -e "${RED}✗${NC} Critical: $CRITICAL_MISSING (required tools missing)"
echo ""

if [ $CRITICAL_MISSING -eq 0 ]; then
  echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}🎉 All critical requirements met!${NC}"
  echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"

  if [ $WARNING_COUNT -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}ℹ${NC} Consider installing optional tools for best experience."
  fi

  exit 0
else
  echo -e "${RED}════════════════════════════════════════════════════════${NC}"
  echo -e "${RED}❌ $CRITICAL_MISSING critical requirement(s) missing!${NC}"
  echo -e "${RED}════════════════════════════════════════════════════════${NC}"
  echo ""
  echo -e "${YELLOW}→${NC} Please install the missing tools above before continuing."
  echo ""
  exit 1
fi
