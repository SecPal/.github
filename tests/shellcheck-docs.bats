#!/usr/bin/env bats
# SPDX-FileCopyrightText: 2025 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Tests for shellcheck-docs.sh

setup() {
    TMPDIR=$(mktemp -d)
    SCRIPT="./scripts/shellcheck-docs.sh"
}

teardown() {
    rm -rf "$TMPDIR"
}

@test "shellcheck-docs: detects missing nullglob" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
for file in *.sh; do
    echo "$file"
done
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Missing 'shopt -s nullglob'" ]]
}

@test "shellcheck-docs: passes with nullglob" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
shopt -s nullglob
for file in *.sh; do
    echo "$file"
done
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "shellcheck-docs: detects piped while loop" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
echo "data" | while read line; do
    exit 1
done
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "Piped while loop" ]]
}

@test "shellcheck-docs: detects mktemp without atomic permissions" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
TMPDIR=$(mktemp -d)
chmod 700 "$TMPDIR"
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "mktemp without atomic permissions" ]]
}

@test "shellcheck-docs: passes with atomic mktemp" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
TMPDIR=$(umask 077; mktemp -d)
trap 'rm -rf -- "$TMPDIR"' EXIT
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
}

@test "shellcheck-docs: detects missing trap cleanup" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
TMPDIR=$(mktemp -d)
# do work
rm -rf "$TMPDIR"
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "mktemp without trap cleanup" ]]
}

@test "shellcheck-docs: detects rm -rf without --" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
TMPDIR="/tmp/test"
rm -rf "$TMPDIR"
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "rm -rf without '--' protection" ]]
}

@test "shellcheck-docs: detects read without -r" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

```bash
while read LINE; do
    echo "$LINE"
done
```
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 1 ]
    [[ "$output" =~ "read without -r" ]]
}

@test "shellcheck-docs: no bash blocks returns success" {
    cat > "$TMPDIR/test.md" << 'EOF'
# Test

This is just markdown text.
EOF

    run "$SCRIPT" "$TMPDIR/test.md"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "No bash blocks found" ]]
}

@test "shellcheck-docs: multiple files" {
    cat > "$TMPDIR/good.md" << 'EOF'
```bash
shopt -s nullglob
for file in *.sh; do
    echo "$file"
done
```
EOF

    cat > "$TMPDIR/bad.md" << 'EOF'
```bash
for file in *.sh; do
    echo "$file"
done
```
EOF

    run "$SCRIPT" "$TMPDIR/good.md" "$TMPDIR/bad.md"
    [ "$status" -eq 1 ]
}
