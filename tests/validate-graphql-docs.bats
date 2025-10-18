#!/usr/bin/env bats
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Tests for validate-graphql-docs.sh

setup() {
    TMPDIR=$(mktemp -d)
    SCRIPT="./scripts/validate-graphql-docs.sh"
}

teardown() {
    rm -rf "$TMPDIR"
}

@test "graphql: detects single-quoted query with variable" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $PR_NUMBER) {
      id
    }
  }
}'
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Single-quoted query with variable" ]]
}

@test "graphql: detects hardcoded owner" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api graphql -f query="
query {
  repository(owner: \"SecPal\", name: \".github\") {
    id
  }
}"
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Hardcoded owner" ]]
}

@test "graphql: detects pagination without pageInfo" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api graphql -f query='
query($number: Int!) {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { id }
      }
    }
  }
}' -f number=42
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Pagination used.*without pageInfo" ]]
}

@test "graphql: passes with proper pagination" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api graphql -f query='
query($number: Int!) {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { id }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}' -f number=42
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "graphql: detects mismatched braces" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api graphql -f query='
query {
  repository(owner: "SecPal") {
    id
  # Missing closing brace
}'
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Mismatched braces" ]]
}

@test "graphql: detects variable used but not declared" {
    cat > "$TMPDIR/test.md" << 'EOF'
```bash
gh api graphql -f query='
query {
  repository(owner: "SecPal", name: ".github") {
    pullRequest(number: $number) {
      id
    }
  }
}'
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Variable.*used but not declared" ]]
}

@test "graphql: no queries returns success" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

This is just markdown text.
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "No GraphQL queries found" ]]
}
