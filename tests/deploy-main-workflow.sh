#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression checks for the main-branch VPS deployment workflow.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/deploy-main.yml"

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

marker_count="$(grep -c '^---$' "$WORKFLOW")"
if [ "$marker_count" -ne 1 ]; then
  echo "Deploy workflow must contain exactly one YAML document marker." >&2
  exit 1
fi

if [ "$(sed -n '1p' "$WORKFLOW")" != '# SPDX-FileCopyrightText: 2026 SecPal' ]; then
  echo "Deploy workflow must start with the SPDX copyright header." >&2
  exit 1
fi

license_header_prefix='# SPDX-License'
if [ "$(sed -n '2p' "$WORKFLOW")" != "${license_header_prefix}-Identifier: AGPL-3.0-or-later" ]; then
  echo "Deploy workflow must declare the AGPL SPDX license header." >&2
  exit 1
fi

grep -q '^name: Deploy main to VPS$' "$WORKFLOW" || {
  echo "Deploy workflow must declare its workflow name." >&2
  exit 1
}

grep -q '^permissions:$' "$WORKFLOW" || {
  echo "Deploy workflow must declare explicit permissions." >&2
  exit 1
}

permissions_block="$(awk '
  /^permissions:$/ { in_block = 1; print; next }
  in_block && /^[^[:space:]]/ { exit }
  in_block { print }
' "$WORKFLOW")"

expected_permissions_block='permissions:
  contents: read'

if [ "$permissions_block" != "$expected_permissions_block" ]; then
  echo "Deploy workflow must keep exact least-privilege contents: read permissions." >&2
  exit 1
fi

grep -q '^    timeout-minutes: 10$' "$WORKFLOW" || {
  echo "Deploy workflow must set timeout-minutes on the deploy job." >&2
  exit 1
}

grep -q '^      - main$' "$WORKFLOW" || {
  echo "Deploy workflow must trigger on pushes to main." >&2
  exit 1
}

grep -q '^  group: deploy-main-\${{ github.event.repository.name }}$' "$WORKFLOW" || {
  echo "Deploy workflow must scope concurrency by repository name." >&2
  exit 1
}

grep -q '^  cancel-in-progress: false$' "$WORKFLOW" || {
  echo "Deploy workflow must queue newer deployments instead of canceling an active deployment." >&2
  exit 1
}

grep -q '^          VPS_HOST: \${{ secrets.VPS_HOST }}$' "$WORKFLOW" || {
  echo "Deploy workflow must source VPS_HOST from GitHub secrets." >&2
  exit 1
}

grep -q '^          VPS_KNOWN_HOSTS: \${{ secrets.VPS_KNOWN_HOSTS }}$' "$WORKFLOW" || {
  echo "Deploy workflow must source VPS_KNOWN_HOSTS from GitHub secrets." >&2
  exit 1
}

grep -Fq 'trap '\''rm -f ~/.ssh/vps_key ~/.ssh/known_hosts'\'' EXIT' "$WORKFLOW" || {
  echo "Deploy workflow must clean up the temporary SSH key material." >&2
  exit 1
}

grep -Fq 'ssh \' "$WORKFLOW" || {
  echo "Deploy workflow must execute the remote deployment over SSH." >&2
  exit 1
}

grep -Fq 'quote_remote_word() {' "$WORKFLOW" || {
  echo "Deploy workflow must shell-quote the repository name for the remote shell." >&2
  exit 1
}

grep -Fq 'REMOTE_REPO_NAME="$(quote_remote_word "$REPO_NAME")"' "$WORKFLOW" || {
  echo "Deploy workflow must prepare a shell-quoted repository name." >&2
  exit 1
}

grep -Fq '"sh -lc '\''deploy \"\$1\"'\'' deploy $REMOTE_REPO_NAME"' "$WORKFLOW" || {
  echo "Deploy workflow must pass the repository name as a positional argument to the remote deploy command." >&2
  exit 1
}

remote_output="$(
  env -i PATH="/usr/bin:/bin" \
    sh -c "sh -lc 'printf \"argc=%s arg1=%s\\n\" \"\$#\" \"\$1\"' deploy 'shiny-pelican'"
)"

if [ "$remote_output" != 'argc=1 arg1=shiny-pelican' ]; then
  echo "Deploy workflow remote command must pass exactly one repository argument." >&2
  exit 1
fi

quote_remote_word() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

quoted_repo_name="$(quote_remote_word "shiny' pelican; echo bad")"
quoted_remote_output="$(
  env -i PATH="/usr/bin:/bin" \
    sh -c "sh -lc 'printf \"argc=%s arg1=%s\\n\" \"\$#\" \"\$1\"' deploy $quoted_repo_name"
)"

if [ "$quoted_remote_output" != "argc=1 arg1=shiny' pelican; echo bad" ]; then
  echo "Deploy workflow remote repository-name quoting must preserve one argument." >&2
  exit 1
fi

echo "tests/deploy-main-workflow.sh: deploy-main workflow verified."
