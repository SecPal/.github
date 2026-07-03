#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

sandbox="$(mktemp -d "${TMPDIR:-/tmp}/check-system-requirements.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

workspace="$sandbox/workspace"
mkdir -p "$workspace/.github/scripts" "$workspace/android/android" "$workspace/android/node_modules/.bin" "$workspace/bin"

cp "$REPO_ROOT/scripts/check-system-requirements.sh" "$workspace/.github/scripts/check-system-requirements.sh"
chmod +x "$workspace/.github/scripts/check-system-requirements.sh"

cat >"$workspace/android/package.json" <<'JSON'
{
  "name": "@secpal/android-test",
  "private": true,
  "dependencies": {},
  "devDependencies": {
    "typescript": "1.0.0",
    "vite": "1.0.0",
    "vitest": "1.0.0",
    "eslint": "1.0.0"
  }
}
JSON

stub_command() {
  local name="$1"
  local body="$2"
  cat >"$workspace/bin/$name" <<EOF
#!/usr/bin/env bash
set -euo pipefail
$body
EOF
  chmod +x "$workspace/bin/$name"
}

link_system_command() {
  local name="$1"
  ln -sf "$(command -v "$name")" "$workspace/bin/$name"
}

# shellcheck disable=SC2016
stub_command "git" '
if [ "${1:-}" = "config" ] && [ "${2:-}" = "--get" ] && [ "${3:-}" = "user.name" ]; then
  echo "SecPal Tester"
  exit 0
fi
if [ "${1:-}" = "config" ] && [ "${2:-}" = "--get" ] && [ "${3:-}" = "user.email" ]; then
  echo "tester@secpal.app"
  exit 0
fi
if [ "${1:-}" = "config" ] && [ "${2:-}" = "--get" ] && [ "${3:-}" = "commit.gpgsign" ]; then
  echo "true"
  exit 0
fi
exit 0
'
stub_command "curl" 'exit 0'
stub_command "jq" 'exit 0'
stub_command "reuse" 'exit 0'
# shellcheck disable=SC2016
stub_command "npx" '
if [ "${*: -1}" = "--version" ]; then
  echo "1.0.0"
fi
exit 0
'
stub_command "shellcheck" 'exit 0'
stub_command "node" 'echo "v22.1.0"'
# shellcheck disable=SC2016
stub_command "npm" '
if [ "${1:-}" = "list" ]; then
  exit 0
fi
echo "10.0.0"
'
# shellcheck disable=SC2016
stub_command "java" '
if [ "${1:-}" = "-version" ]; then
  echo "openjdk version \"21.0.11\""
  exit 0
fi
exit 0
'
stub_command "javac" 'echo "javac 21.0.11"'
stub_command "adb" 'echo "Android Debug Bridge version 1.0.41"'
stub_command "sdkmanager" 'echo "25.2.0"'
link_system_command "grep"
link_system_command "sed"
link_system_command "cut"
link_system_command "head"
link_system_command "awk"
link_system_command "bash"
link_system_command "cat"
link_system_command "dirname"
link_system_command "pwd"

run_check() {
  local output_file="$1"
  shift
  (
    cd "$workspace/.github"
    PATH="$workspace/bin" /bin/bash ./scripts/check-system-requirements.sh "$@"
  ) >"$output_file" 2>&1
}

success_output="$sandbox/success.txt"
if ! run_check "$success_output" --repo=android; then
  cat "$success_output"
  echo "android requirements check unexpectedly failed on happy path" >&2
  exit 1
fi

grep -Fq '5. Android Repository (Capacitor + Native Android Toolchain)' "$success_output"
grep -Fq 'Java 21' "$success_output"
grep -Fq 'Android SDK Command-Line Tools (sdkmanager)' "$success_output"
grep -Fq 'Android SDK Platform-Tools (adb)' "$success_output"
grep -Fq 'TypeScript installed' "$success_output"
grep -Fq 'Vitest installed' "$success_output"
grep -Fq 'All critical requirements met!' "$success_output"

rm -f "$workspace/bin/sdkmanager"

failure_output="$sandbox/failure.txt"
if run_check "$failure_output" --repo=android; then
  cat "$failure_output"
  echo "android requirements check unexpectedly succeeded without sdkmanager" >&2
  exit 1
fi

grep -Fq 'Android SDK Command-Line Tools (sdkmanager)' "$failure_output"

echo "tests/check-system-requirements.sh: android happy and missing-sdkmanager paths verified."
