#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PACKAGE_JSON_PATH="${PRETTIER_ALIGNMENT_PACKAGE_JSON:-$REPO_ROOT/package.json}"
PRE_COMMIT_CONFIG_PATH="${PRETTIER_ALIGNMENT_PRE_COMMIT_CONFIG:-$REPO_ROOT/.pre-commit-config.yaml}"
PREFLIGHT_SCRIPT_PATH="${PRETTIER_ALIGNMENT_PREFLIGHT_SCRIPT:-$REPO_ROOT/scripts/preflight.sh}"
QUALITY_WORKFLOW_PATH="${PRETTIER_ALIGNMENT_QUALITY_WORKFLOW:-$REPO_ROOT/.github/workflows/quality.yml}"

extract_package_prettier_version() {
  local package_json_path="$1"
  local version=""

  if command -v node >/dev/null 2>&1; then
    version="$(node -e '
      const fs = require("fs");
      const pkg = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
      const v = pkg.devDependencies?.prettier ?? pkg.dependencies?.prettier ?? "";
      if (!v) process.exit(1);
      process.stdout.write(String(v));
    ' "$package_json_path" 2>/dev/null || true)"
  elif command -v python3 >/dev/null 2>&1; then
    version="$(python3 - "$package_json_path" <<'PY' 2>/dev/null || true
import json
import sys

package_json = sys.argv[1]

with open(package_json, "r", encoding="utf-8") as fh:
    pkg = json.load(fh)

version = (
    (pkg.get("devDependencies") or {}).get("prettier")
    or (pkg.get("dependencies") or {}).get("prettier")
    or ""
)

if version:
    print(version, end="")
else:
    raise SystemExit(1)
PY
)"
  else
    version="$(sed -nE 's/^[[:space:]]*"prettier"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$package_json_path" | head -n 1)"
  fi

  if [ -z "$version" ]; then
    echo "Unable to read prettier version from $package_json_path (expected devDependencies.prettier or dependencies.prettier)." >&2
    return 1
  fi

  printf '%s\n' "$version"
}

assert_contains_expected_pin() {
  local path="$1"
  local expected_version="$2"
  local label="$3"
  local matches

  matches="$(grep -Eo 'prettier@[0-9]+\.[0-9]+\.[0-9]+' "$path" || true)"
  if [ -z "$matches" ]; then
    echo "$label does not pin prettier with prettier@X.Y.Z: $path" >&2
    return 1
  fi

  local unique_versions
  unique_versions="$(printf '%s\n' "$matches" | sed 's/^prettier@//' | sort -u)"

  if [ "$unique_versions" != "$expected_version" ]; then
    echo "$label prettier version drift in $path" >&2
    echo "  expected from package.json: $expected_version" >&2
    echo "  found pinned version(s): $(printf '%s' "$unique_versions" | tr '\n' ' ' | sed 's/[[:space:]]*$//')" >&2
    return 1
  fi
}

assert_quality_workflow_uses_package_lock_step() {
  local path="$1"

  if ! grep -Fq 'run: npm ci' "$path"; then
    echo "Quality workflow must install pinned dependencies with 'npm ci': $path" >&2
    return 1
  fi

  if ! grep -Fq "run: npx prettier --check" "$path"; then
    echo "Quality workflow must run prettier from installed dependencies: $path" >&2
    return 1
  fi

  if grep -Eq 'run:[[:space:]]+npx[[:space:]]+prettier@[0-9]' "$path"; then
    echo "Quality workflow must not pin a separate prettier@X.Y.Z; it must use package.json via npm ci: $path" >&2
    return 1
  fi
}

check_alignment() {
  local expected_version="$1"
  local package_json_path="$2"
  local pre_commit_config_path="$3"
  local preflight_script_path="$4"
  local quality_workflow_path="$5"

  if [ ! -f "$package_json_path" ]; then
    echo "Missing package.json for prettier alignment check: $package_json_path" >&2
    return 1
  fi
  if [ ! -f "$pre_commit_config_path" ]; then
    echo "Missing pre-commit config for prettier alignment check: $pre_commit_config_path" >&2
    return 1
  fi
  if [ ! -f "$preflight_script_path" ]; then
    echo "Missing preflight script for prettier alignment check: $preflight_script_path" >&2
    return 1
  fi
  if [ ! -f "$quality_workflow_path" ]; then
    echo "Missing quality workflow for prettier alignment check: $quality_workflow_path" >&2
    return 1
  fi

  assert_contains_expected_pin "$pre_commit_config_path" "$expected_version" ".pre-commit-config.yaml" || return 1
  assert_contains_expected_pin "$preflight_script_path" "$expected_version" "scripts/preflight.sh" || return 1
  assert_quality_workflow_uses_package_lock_step "$quality_workflow_path" || return 1
}

run_negative_scenario() {
  local expected_version="$1"
  local package_json_path="$2"
  local pre_commit_config_path="$3"
  local preflight_script_path="$4"
  local quality_workflow_path="$5"
  local scratch

  scratch="$(mktemp -d "${TMPDIR:-/tmp}/prettier-version-alignment.XXXXXX")"
  trap 'rm -rf "'"$scratch"'"' RETURN EXIT

  cp "$package_json_path" "$scratch/package.json"
  cp "$pre_commit_config_path" "$scratch/.pre-commit-config.yaml"
  cp "$preflight_script_path" "$scratch/preflight.sh"
  cp "$quality_workflow_path" "$scratch/quality.yml"

  local wrong_version="0.0.0"
  if [ "$wrong_version" = "$expected_version" ]; then
    wrong_version="9.9.9"
  fi

  sed -i.bak -E "s/prettier@[0-9]+\.[0-9]+\.[0-9]+/prettier@$wrong_version/g" "$scratch/preflight.sh"
  rm -f "$scratch/preflight.sh.bak"

  local output_file="$scratch/negative-output.txt"
  local exit_code=0
  if check_alignment "$expected_version" \
    "$scratch/package.json" \
    "$scratch/.pre-commit-config.yaml" \
    "$scratch/preflight.sh" \
    "$scratch/quality.yml" >"$output_file" 2>&1; then
    exit_code=0
  else
    exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    echo "Negative scenario failed: mismatch fixture unexpectedly passed prettier alignment checks." >&2
    cat "$output_file" >&2
    return 1
  fi

  if ! grep -Fq 'scripts/preflight.sh prettier version drift' "$output_file"; then
    echo "Negative scenario failed: mismatch fixture did not produce the expected drift message." >&2
    cat "$output_file" >&2
    return 1
  fi
}

main() {
  local expected_version
  expected_version="$(extract_package_prettier_version "$PACKAGE_JSON_PATH")"

  check_alignment \
    "$expected_version" \
    "$PACKAGE_JSON_PATH" \
    "$PRE_COMMIT_CONFIG_PATH" \
    "$PREFLIGHT_SCRIPT_PATH" \
    "$QUALITY_WORKFLOW_PATH"

  run_negative_scenario \
    "$expected_version" \
    "$PACKAGE_JSON_PATH" \
    "$PRE_COMMIT_CONFIG_PATH" \
    "$PREFLIGHT_SCRIPT_PATH" \
    "$QUALITY_WORKFLOW_PATH"
}

main "$@"
