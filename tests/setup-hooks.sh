#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ALL_REPOS=(api frontend contracts android secpal.app guardguide.de changelog .github)

# Single portable mktemp invocation (matches the regression guard in
# tests/mktemp-portability.sh); each scenario gets its own subdirectory below.
sandbox="$(mktemp -d "${TMPDIR:-/tmp}/setup-hooks.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

happy_workspace="$sandbox/happy"
warning_workspace="$sandbox/warning"
corrupt_workspace="$sandbox/corrupt"
failure_workspace="$sandbox/failure"
mkdir -p "$happy_workspace" "$warning_workspace" "$corrupt_workspace" "$failure_workspace"

setup_workspace() {
  local workspace="$1"
  shift
  local repos=("$@")

  mkdir -p "$workspace/.github/scripts"
  cp "$REPO_ROOT/setup-hooks.sh" "$workspace/.github/setup-hooks.sh"
  cp "$REPO_ROOT/scripts/strip-ai-trailers.sh" "$workspace/.github/scripts/strip-ai-trailers.sh"
  chmod +x "$workspace/.github/scripts/strip-ai-trailers.sh"

  mkdir -p "$workspace/bin"
  cat >"$workspace/bin/pre-commit" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
  chmod +x "$workspace/bin/pre-commit"

  for repo in "${repos[@]}"; do
    create_repo "$workspace" "$repo"
  done
}

create_repo() {
  local workspace="$1"
  local repo="$2"

  mkdir -p "$workspace/$repo/scripts"
  # Initialize a real git repo so `git rev-parse --git-path hooks` works for the
  # commit-msg symlink installation.
  git -C "$workspace/$repo" init -q

  cat >"$workspace/$repo/scripts/setup-pre-push.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  cat >"$workspace/$repo/scripts/setup-pre-commit.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  chmod +x "$workspace/$repo/scripts/setup-pre-push.sh" "$workspace/$repo/scripts/setup-pre-commit.sh"
}

run_setup_hooks() {
  local workspace="$1"
  local output_file="$2"
  local rc=0

  set +e
  PATH="$workspace/bin:$PATH" bash "$workspace/.github/setup-hooks.sh" >"$output_file" 2>&1
  rc=$?
  set -e
  return "$rc"
}

# ─── Happy path: every documented repo is present ────────────────────────────
setup_workspace "$happy_workspace" "${ALL_REPOS[@]}"

happy_output="$happy_workspace/output.txt"
if ! run_setup_hooks "$happy_workspace" "$happy_output"; then
  cat "$happy_output"
  echo "happy-path setup-hooks.sh unexpectedly failed" >&2
  exit 1
fi

happy_expected_hooks=$(( ${#ALL_REPOS[@]} * 3 ))
grep -q "Successfully installed: ${happy_expected_hooks} hooks" "$happy_output"
grep -q 'All Git hooks have been successfully installed' "$happy_output"
if grep -q 'Skipped (missing directory)' "$happy_output"; then
  cat "$happy_output"
  echo "happy-path output should not report skipped repositories" >&2
  exit 1
fi
if grep -q '^Failed: ' "$happy_output"; then
  cat "$happy_output"
  echo "happy-path output should not report failed repositories" >&2
  exit 1
fi

# ─── Warning path: a managed repo directory is missing ───────────────────────
# The expectation is documented in SecPal/.github#485: missing managed repos
# must surface as a warning so workspaces that have not synced the latest REPOS
# list (for example after a fresh repo is added) still install hooks for the
# repos they do have, instead of failing the whole script.
warning_present_repos=(api frontend contracts android secpal.app changelog .github)
setup_workspace "$warning_workspace" "${warning_present_repos[@]}"

warning_output="$warning_workspace/output.txt"
if ! run_setup_hooks "$warning_workspace" "$warning_output"; then
  cat "$warning_output"
  echo "warning-path setup-hooks.sh unexpectedly failed (missing repo must be a warning, not an error)" >&2
  exit 1
fi

grep -q 'Directory not found: guardguide.de' "$warning_output"
grep -q 'Skipped (missing directory): 1 repositories' "$warning_output"
grep -q '.github/scripts/install-polyscope-rollout.sh' "$warning_output"
grep -q 'All Git hooks have been successfully installed' "$warning_output"

warning_expected_hooks=$(( ${#warning_present_repos[@]} * 3 ))
grep -q "Successfully installed: ${warning_expected_hooks} hooks" "$warning_output"

if grep -q '^Failed: ' "$warning_output"; then
  cat "$warning_output"
  echo "warning-path output must not report Failed repositories for missing directories" >&2
  exit 1
fi

# ─── Corrupt path: managed repo path exists but is not a directory ───────────
# Only a truly missing repo should soft-warn. If the path exists as a regular
# file, the workspace is corrupted and setup-hooks.sh must fail loudly.
corrupt_present_repos=(api frontend contracts android secpal.app changelog .github)
setup_workspace "$corrupt_workspace" "${corrupt_present_repos[@]}"
printf 'not a directory\n' >"$corrupt_workspace/guardguide.de"

corrupt_output="$corrupt_workspace/output.txt"
if run_setup_hooks "$corrupt_workspace" "$corrupt_output"; then
  cat "$corrupt_output"
  echo "corrupt-path setup-hooks.sh unexpectedly succeeded (non-directory managed path must fail)" >&2
  exit 1
fi

grep -q '^Failed: 1 repositories' "$corrupt_output"
grep -q 'guardguide.de (path is not a directory)' "$corrupt_output"
if grep -q '^Skipped (missing directory): ' "$corrupt_output"; then
  cat "$corrupt_output"
  echo "corrupt-path output must not treat a regular file as a missing directory" >&2
  exit 1
fi

# ─── Failure path: a real installation step fails ────────────────────────────
# Even with the soft-warn change, breakage in a hook installation step (e.g.
# setup-pre-push.sh exits non-zero) must still fail the script with exit 1.
setup_workspace "$failure_workspace" "${ALL_REPOS[@]}"
cat >"$failure_workspace/api/scripts/setup-pre-push.sh" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
chmod +x "$failure_workspace/api/scripts/setup-pre-push.sh"

failure_output="$failure_workspace/output.txt"
if run_setup_hooks "$failure_workspace" "$failure_output"; then
  cat "$failure_output"
  echo "failure-path setup-hooks.sh unexpectedly succeeded (broken pre-push install must exit non-zero)" >&2
  exit 1
fi

grep -q 'Pre-push hook installation failed' "$failure_output"
grep -q '^Failed: 1 repositories' "$failure_output"
grep -q 'api (pre-push)' "$failure_output"

echo "tests/setup-hooks.sh: happy, warning, corrupt-path, and failure paths verified."
