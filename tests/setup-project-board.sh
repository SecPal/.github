#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

assert_contains() {
  local path="$1"
  local expected="$2"

  if ! grep -Fq "$expected" "$path"; then
    echo "Expected to find '$expected' in $path" >&2
    exit 1
  fi
}

assert_not_contains() {
  local path="$1"
  local unexpected="$2"

  if grep -Fq "$unexpected" "$path"; then
    echo "Did not expect to find '$unexpected' in $path" >&2
    exit 1
  fi
}

assert_output_contains() {
  local output="$1"
  local expected="$2"

  if [[ "$output" != *"$expected"* ]]; then
    echo "Expected output to contain '$expected'" >&2
    echo "Actual output:" >&2
    echo "$output" >&2
    exit 1
  fi
}

assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/scripts/setup-project-board.sh" "status: discussion|BFD4F2|Needs decision before implementation"
assert_not_contains "$REPO_ROOT/scripts/setup-project-board.sh" "Specified in feature-requirements.md"

assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "status: discussion|BFD4F2|Needs decision before implementation"
assert_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "The project board is an optional mirrored view"
assert_not_contains "$REPO_ROOT/docs/workflows/QUICK_REFERENCE.md" "Specified in feature-requirements.md"

assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "optional GitHub Project Board mirror"
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "Issues, milestones, and linked PRs remain the source of truth."
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "status: discussion|BFD4F2|Needs decision before implementation"
assert_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "The project board is an optional mirrored view"
assert_not_contains "$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md" "Specified in feature-requirements.md"

run_setup_project_board_integration_tests() {
  local tmp_dir
  tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/setup-project-board.XXXXXX")"
  trap 'rm -rf "$tmp_dir"' RETURN EXIT

  local stub_dir="$tmp_dir/bin"
  mkdir -p "$stub_dir"

  # Scenario 1: gh authentication fails (stub discoverable but exits non-zero)
  cat > "$stub_dir/gh" <<'EOF'
#!/usr/bin/env bash
echo "gh: command not available" >&2
exit 127
EOF
  chmod +x "$stub_dir/gh"

  local output
  set +e
  output="$(
    PATH="$stub_dir:$PATH" \
      bash "$REPO_ROOT/scripts/setup-project-board.sh" 2>&1
  )"
  local status=$?
  set -e
  if [[ $status -eq 0 ]]; then
    echo "Expected failure when gh is unavailable" >&2
    exit 1
  fi
  assert_output_contains "$output" "gh"

  # Scenario 2/3: gh available; simulate prompt branches (no/yes)
  cat > "$stub_dir/gh" <<'EOF'
#!/usr/bin/env bash
# Minimal stub: emulate successful gh operations used by setup script.
exit 0
EOF
  chmod +x "$stub_dir/gh"

  set +e
  output="$(
    printf 'n\n' | PATH="$stub_dir:$PATH" \
      bash "$REPO_ROOT/scripts/setup-project-board.sh" 2>&1
  )"
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    echo "Expected success when declining optional project board setup" >&2
    echo "$output" >&2
    exit 1
  fi

  set +e
  output="$(
    printf 'y\n' | PATH="$stub_dir:$PATH" \
      bash "$REPO_ROOT/scripts/setup-project-board.sh" 2>&1
  )"
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    echo "Expected success when accepting optional project board setup" >&2
    echo "$output" >&2
    exit 1
  fi
}

# Behavioral coverage guard:
# Run integration scenarios (stubbed `gh`, simulated interactive input, and
# branch verification) only when explicitly requested.
if [[ "${REQUIRE_SETUP_PROJECT_BOARD_INTEGRATION_TESTED:-0}" == "1" ]]; then
  run_setup_project_board_integration_tests
fi
