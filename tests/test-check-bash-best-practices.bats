#!/usr/bin/env bats
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Tests for check-bash-best-practices.sh
# Focus: Lesson #24 - Missing 'set -euo pipefail'

setup() {
    TEST_DIR="$(mktemp -d)"
    SCRIPT="$BATS_TEST_DIRNAME/../scripts/check-bash-best-practices.sh"
}

teardown() {
    rm -rf "$TEST_DIR"
}

@test "detects missing set -euo pipefail in workflow" {
    cat > "$TEST_DIR/workflow.yml" << 'EOF'
name: Test
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "No set flags"
EOF

    run "$SCRIPT" "$TEST_DIR/workflow.yml"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Missing 'set -euo pipefail'" ]]
}

@test "accepts workflow with set -euo pipefail" {
    cat > "$TEST_DIR/workflow.yml" << 'EOF'
name: Test
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          set -euo pipefail
          echo "Good"
EOF

    run "$SCRIPT" "$TEST_DIR/workflow.yml"
    [ "$status" -eq 0 ]
}

@test "checks all run blocks in workflow" {
    cat > "$TEST_DIR/workflow.yml" << 'EOF'
name: Test
jobs:
  test:
    steps:
      - run: |
          set -euo pipefail
          echo "Good"
      - run: |
          echo "Bad"
EOF

    run "$SCRIPT" "$TEST_DIR/workflow.yml"
    [ "$status" -eq 1 ]
}

@test "detects missing set -euo pipefail in shell script" {
    cat > "$TEST_DIR/script.sh" << 'EOF'
#!/bin/bash
echo "No set flags"
EOF

    run "$SCRIPT" "$TEST_DIR/script.sh"
    [ "$status" -eq 1 ]
}

@test "accepts shell script with set -euo pipefail" {
    cat > "$TEST_DIR/script.sh" << 'EOF'
#!/bin/bash
set -euo pipefail
echo "Good"
EOF

    run "$SCRIPT" "$TEST_DIR/script.sh"
    [ "$status" -eq 0 ]
}

@test "validates actual copilot-review workflow" {
    WORKFLOW="$BATS_TEST_DIRNAME/../.github/workflows/reusable-copilot-review.yml"

    if [ -f "$WORKFLOW" ]; then
        run "$SCRIPT" "$WORKFLOW"
        [ "$status" -eq 0 ]
    else
        skip "Workflow not found"
    fi
}

@test "validates actual resolve-pr-threads script" {
    SCRIPT_FILE="$BATS_TEST_DIRNAME/../scripts/resolve-pr-threads.sh"

    if [ -f "$SCRIPT_FILE" ]; then
        run "$SCRIPT" "$SCRIPT_FILE"
        [ "$status" -eq 0 ]
    else
        skip "Script not found"
    fi
}

@test "shows usage without arguments" {
    run "$SCRIPT"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Usage" ]]
}

@test "handles non-existent file" {
    run "$SCRIPT" "/non/existent.yml"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "File not found" ]]
}

@test "reports multiple files with issues" {
    skip "Edge case - not critical for Lesson #24 enforcement"
}
