#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

sandbox="$(mktemp -d "${TMPDIR:-/tmp}/check-system-requirements.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

workspace="$sandbox/workspace"
sdk_root="$workspace/polyscope-android-sdk"
test_home="$workspace/home"
mkdir -p \
  "$workspace/.github/scripts" \
  "$workspace/api/vendor/bin" \
  "$workspace/android/android" \
  "$workspace/android/node_modules/.bin" \
  "$workspace/contracts/node_modules/.bin" \
  "$workspace/frontend/node_modules/.bin" \
  "$workspace/bin" \
  "$sdk_root/platform-tools" \
  "$sdk_root/cmdline-tools/latest" \
  "$sdk_root" \
  "$test_home"

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

cat >"$workspace/frontend/package.json" <<'JSON'
{
  "name": "@secpal/frontend-test",
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

cat >"$workspace/contracts/package.json" <<'JSON'
{
  "name": "@secpal/contracts-test",
  "private": true,
  "dependencies": {},
  "devDependencies": {
    "@redocly/cli": "1.0.0"
  }
}
JSON

touch "$workspace/api/vendor/bin/pest" "$workspace/api/vendor/bin/pint" "$workspace/api/vendor/bin/phpstan"
chmod +x "$workspace/api/vendor/bin/pest" "$workspace/api/vendor/bin/pint" "$workspace/api/vendor/bin/phpstan"

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
stub_command "php" 'echo "8.4.0"'
stub_command "composer" 'exit 0'
# shellcheck disable=SC2016
stub_command "node" 'echo "${TEST_NODE_VERSION:-v22.1.0}"'
# shellcheck disable=SC2016
stub_command "npm" '
if [ "${1:-}" = "list" ]; then
  exit 0
fi
echo "10.0.0"
'
stub_command "yarn" 'exit 0'
stub_command "pnpm" 'exit 0'
# shellcheck disable=SC2016
stub_command "java" '
if [ "${1:-}" = "-version" ]; then
  echo "openjdk version \"${TEST_JAVA_VERSION:-21.0.11}\""
  exit 0
fi
exit 0
'
stub_command "javac" 'echo "javac ${TEST_JAVAC_VERSION:-21.0.11}"'
stub_command "adb" 'echo "Android Debug Bridge version 1.0.41"'
stub_command "sdkmanager" 'echo "25.2.0"'
stub_command "gh" 'exit 0'
stub_command "pre-commit" 'exit 0'
stub_command "ssh" 'exit 0'
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
    PATH="$workspace/bin" \
      HOME="$test_home" \
      JAVA_HOME="" \
      POLYSCOPE_ANDROID_SDK_ROOT="$sdk_root" \
      ANDROID_SDK_ROOT="" \
      ANDROID_HOME="" \
      TEST_NODE_VERSION="${TEST_NODE_VERSION:-v22.1.0}" \
      /bin/bash ./scripts/check-system-requirements.sh "$@"
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
grep -Fq "Android SDK directory exists ($sdk_root)" "$success_output"
grep -Fq 'TypeScript installed' "$success_output"
grep -Fq 'Vitest installed' "$success_output"
grep -Fq 'All critical requirements met!' "$success_output"

java_home_dir="$workspace/jdk-21"
mkdir -p "$java_home_dir/bin"
cat >"$java_home_dir/bin/java" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "-version" ]; then
  echo 'openjdk version "21.0.11"'
  exit 0
fi
exit 0
EOF
cat >"$java_home_dir/bin/javac" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
echo 'javac 21.0.11'
EOF
chmod +x "$java_home_dir/bin/java" "$java_home_dir/bin/javac"

java_home_output="$sandbox/java-home-success.txt"
if ! (
  cd "$workspace/.github"
  PATH="$workspace/bin" \
    HOME="$test_home" \
    JAVA_HOME="$java_home_dir" \
    POLYSCOPE_ANDROID_SDK_ROOT="$sdk_root" \
    ANDROID_SDK_ROOT="" \
    ANDROID_HOME="" \
    TEST_JAVA_VERSION="17.0.12" \
    TEST_JAVAC_VERSION="17.0.12" \
    /bin/bash ./scripts/check-system-requirements.sh --repo=android
) >"$java_home_output" 2>&1; then
  cat "$java_home_output"
  echo "android requirements check unexpectedly ignored JAVA_HOME when PATH java was too old" >&2
  exit 1
fi

grep -Fq 'Java 21' "$java_home_output"
grep -Fq 'Java compiler (javac)' "$java_home_output"
grep -Fq 'All critical requirements met!' "$java_home_output"

java_runtime_only_dir="$workspace/jre-21"
mkdir -p "$java_runtime_only_dir/bin"
cat >"$java_runtime_only_dir/bin/java" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "-version" ]; then
  echo 'openjdk version "21.0.11"'
  exit 0
fi
exit 0
EOF
chmod +x "$java_runtime_only_dir/bin/java"

java_runtime_only_output="$sandbox/java-home-runtime-only.txt"
if (
  cd "$workspace/.github"
  PATH="$workspace/bin" \
    HOME="$test_home" \
    JAVA_HOME="$java_runtime_only_dir" \
    JAVA_HOME="$java_runtime_only_dir" \
    POLYSCOPE_ANDROID_SDK_ROOT="$sdk_root" \
    ANDROID_SDK_ROOT="" \
    ANDROID_HOME="" \
    TEST_JAVA_VERSION="17.0.12" \
    TEST_JAVAC_VERSION="17.0.12" \
    /bin/bash ./scripts/check-system-requirements.sh --repo=android
) >"$java_runtime_only_output" 2>&1; then
  cat "$java_runtime_only_output"
  echo "android requirements check unexpectedly succeeded with JAVA_HOME runtime but PATH javac only" >&2
  exit 1
fi

grep -Fq 'Java 21' "$java_runtime_only_output"
grep -Fq 'Java compiler (javac)' "$java_runtime_only_output"
grep -Fq 'critical requirement(s) missing' "$java_runtime_only_output"

old_node_output="$sandbox/node-too-old.txt"
if TEST_NODE_VERSION="v20.15.0" run_check "$old_node_output" --repo=android; then
  cat "$old_node_output"
  echo "android requirements check unexpectedly succeeded with Node.js 20" >&2
  exit 1
fi

grep -Fq 'Node.js v20.15.0' "$old_node_output"
grep -Fq '>= 22.x required' "$old_node_output"

all_repos_old_node_output="$sandbox/all-repos-node-too-old.txt"
if TEST_NODE_VERSION="v20.15.0" run_check "$all_repos_old_node_output"; then
  cat "$all_repos_old_node_output"
  echo "all-repositories requirements check unexpectedly succeeded with Node.js 20 and sibling android repo" >&2
  exit 1
fi

grep -Fq '3. Frontend Repository (React + TypeScript + Node)' "$all_repos_old_node_output"
grep -Fq '5. Android Repository (Capacitor + Native Android Toolchain)' "$all_repos_old_node_output"
grep -Fq 'Node.js v20.15.0' "$all_repos_old_node_output"
grep -Fq '>= 22.x required' "$all_repos_old_node_output"

mv "$workspace/android" "$workspace/android-hidden"

missing_repo_output="$sandbox/missing-repo.txt"
if ! run_check "$missing_repo_output" --repo=android; then
  cat "$missing_repo_output"
  echo "android requirements check unexpectedly failed without sibling android repo" >&2
  exit 1
fi

if grep -Fq 'Android Repository - Local Dependencies' "$missing_repo_output"; then
  cat "$missing_repo_output"
  echo "android requirements check unexpectedly printed local dependencies header without sibling repo" >&2
  exit 1
fi

mv "$workspace/android-hidden" "$workspace/android"

rm -f "$workspace/bin/sdkmanager"

failure_output="$sandbox/failure.txt"
if run_check "$failure_output" --repo=android; then
  cat "$failure_output"
  echo "android requirements check unexpectedly succeeded without sdkmanager" >&2
  exit 1
fi

grep -Fq 'Android SDK Command-Line Tools (sdkmanager)' "$failure_output"
grep -Fq 'Android SDK Platform-Tools (adb)' "$failure_output"
grep -Fq "Android SDK directory exists ($sdk_root)" "$failure_output"
grep -Fq 'Native Android project directory exists' "$failure_output"
grep -Fq 'TypeScript installed' "$failure_output"

echo "tests/check-system-requirements.sh: android happy and missing-sdkmanager paths verified."
