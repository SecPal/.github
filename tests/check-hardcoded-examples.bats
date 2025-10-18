#!/usr/bin/env bats
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Tests for check-hardcoded-examples.sh

setup() {
    TMPDIR=$(mktemp -d)
    SCRIPT="./scripts/check-hardcoded-examples.sh"
}

teardown() {
    rm -rf "$TMPDIR"
}

@test "hardcoding: detects hardcoded PR number" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
PR_NUMBER=42
gh pr view $PR_NUMBER
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Hardcoded PR number" ]]
}

@test "hardcoding: allows PR_NUMBER in examples" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

Example: PR_NUMBER=42
```bash
PR_NUMBER=$1
gh pr view $PR_NUMBER
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "hardcoding: detects hardcoded GraphQL owner" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: 42) {
      id
    }
  }
}'
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Hardcoded owner" ]]
}

@test "hardcoding: detects incorrect markdown escaping" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

The PRRT*\* identifier is wrong.
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Incorrect markdown escaping" ]]
}

@test "hardcoding: passes with backticks" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

The `PRRT_*` identifier is correct.
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "hardcoding: detects hardcoded repo name" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api repos/SecPal/.github/pulls/42
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
}

@test "hardcoding: allows examples with e.g." {
    cat > "$TMPDIR/test.md" << 'EOF'
Usage: script.sh <owner>/<repo>
Example: script.sh SecPal/.github (e.g., for testing)
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "hardcoding: multiple files" {
    cat > "$TMPDIR/good.md" << 'EOF'
```bash
OWNER=$1
REPO=$2
gh api repos/$OWNER/$REPO
```
EOF

    cat > "$TMPDIR/bad.md" << 'EOF'
```bash
gh api repos/SecPal/.github
```
EOF

    run "$SCRIPT" "$TMPDIR/good.md" "$TMPDIR/bad.md"
    [ "$status" -eq 1 ]
}
