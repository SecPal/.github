#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression checks for the main-branch VPS deployment workflows.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_WORKFLOW="$REPO_ROOT/.github/workflows/deploy-main.yml"
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-deploy-main.yml"

for workflow in "$CALLER_WORKFLOW" "$REUSABLE_WORKFLOW"; do
  if [ ! -f "$workflow" ]; then
    echo "Expected workflow was not found: $workflow" >&2
    exit 1
  fi

  marker_count="$(grep -c '^---$' "$workflow")"
  if [ "$marker_count" -ne 1 ]; then
    echo "Deploy workflow must contain exactly one YAML document marker: $workflow" >&2
    exit 1
  fi
done

if [ "$(sed -n '1p' "$CALLER_WORKFLOW")" != '# SPDX-FileCopyrightText: 2026 SecPal' ]; then
  echo "Deploy caller workflow must start with the SPDX copyright header." >&2
  exit 1
fi

license_header_prefix='# SPDX-License'
if [ "$(sed -n '2p' "$CALLER_WORKFLOW")" != "${license_header_prefix}-Identifier: AGPL-3.0-or-later" ]; then
  echo "Deploy caller workflow must declare the AGPL SPDX license header." >&2
  exit 1
fi

grep -q '^name: Deploy main to VPS$' "$CALLER_WORKFLOW" || {
  echo "Deploy caller workflow must declare its workflow name." >&2
  exit 1
}

grep -q '^name: Reusable Deploy to VPS$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must declare its workflow name." >&2
  exit 1
}

permissions_block="$(awk '
  /^permissions:$/ { in_block = 1; print; next }
  in_block && /^[^[:space:]]/ { exit }
  in_block { print }
' "$CALLER_WORKFLOW")"

expected_permissions_block='permissions:
  contents: read'

if [ "$permissions_block" != "$expected_permissions_block" ]; then
  echo "Deploy caller workflow must keep exact least-privilege contents: read permissions." >&2
  exit 1
fi

reusable_permissions_line="$(awk '/^permissions:/ { print; exit }' "$REUSABLE_WORKFLOW")"
if [ "$reusable_permissions_line" != 'permissions: {}' ]; then
  echo "Reusable deploy workflow must declare explicit empty token permissions." >&2
  exit 1
fi

grep -q '^      - main$' "$CALLER_WORKFLOW" || {
  echo "Deploy caller workflow must trigger on pushes to main." >&2
  exit 1
}

grep -q '^  workflow_call:$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must be callable via workflow_call." >&2
  exit 1
}

grep -q '^  group: deploy-main-\${{ github.event.repository.name }}$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must scope concurrency by repository name." >&2
  exit 1
}

grep -q '^  cancel-in-progress: false$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must queue newer deployments instead of canceling an active deployment." >&2
  exit 1
}

grep -q '^    uses: SecPal/\.github/\.github/workflows/reusable-deploy-main\.yml@main$' "$CALLER_WORKFLOW" || {
  echo "Deploy caller workflow must invoke the reusable deploy workflow from @main." >&2
  exit 1
}

if grep -q '^    secrets: inherit$' "$CALLER_WORKFLOW"; then
  echo "Deploy caller workflow must not inherit every caller secret into the reusable deploy workflow." >&2
  exit 1
fi

for secret_name in VPS_HOST VPS_PORT VPS_USER VPS_SSH_KEY VPS_KNOWN_HOSTS; do
  grep -q "^      ${secret_name}: \${{ secrets\.${secret_name} }}$" "$CALLER_WORKFLOW" || {
    echo "Deploy caller workflow must map ${secret_name} explicitly into the reusable deploy workflow." >&2
    exit 1
  }
done

if awk '
  /^  deploy:$/ { in_job = 1; next }
  in_job && /^  [[:alnum:]_-]+:$/ { in_job = 0 }
  in_job && /^[[:space:]]+uses: SecPal\/\.github\/\.github\/workflows\/reusable-deploy-main\.yml@main$/ {
    reusable_job = 1
  }
  in_job && /^[[:space:]]+timeout-minutes:/ { has_timeout = 1 }
  END { exit !(reusable_job && has_timeout) }
' "$CALLER_WORKFLOW"; then
  echo "Deploy caller workflow must not set timeout-minutes on a reusable workflow caller job." >&2
  exit 1
fi

grep -q '^    timeout-minutes: 10$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must set timeout-minutes on the deploy job." >&2
  exit 1
}

for secret_name in VPS_HOST VPS_PORT VPS_USER VPS_SSH_KEY VPS_KNOWN_HOSTS; do
  grep -q "^      ${secret_name}:$" "$REUSABLE_WORKFLOW" || {
    echo "Reusable deploy workflow must declare ${secret_name} as a workflow_call secret." >&2
    exit 1
  }

  grep -q "^          ${secret_name}: \${{ secrets\.${secret_name} }}$" "$REUSABLE_WORKFLOW" || {
    echo "Reusable deploy workflow must source ${secret_name} from GitHub secrets." >&2
    exit 1
  }
done

grep -Fq 'trap '\''rm -f ~/.ssh/vps_key ~/.ssh/known_hosts'\'' EXIT' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must clean up the temporary SSH key material." >&2
  exit 1
}

grep -Fq 'quote_remote_word() {' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must shell-quote the repository name for the remote shell." >&2
  exit 1
}

grep -Fq 'REMOTE_REPO_NAME="$(quote_remote_word "$REPO_NAME")"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must prepare a shell-quoted repository name." >&2
  exit 1
}

grep -Fq '"sh -c '\''deploy \"\$1\"'\'' deploy $REMOTE_REPO_NAME"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable deploy workflow must pass the repository name as a positional argument without using a login shell." >&2
  exit 1
}

if grep -Fq '"sh -lc '\''deploy \"\$1\"'\'' deploy $REMOTE_REPO_NAME"' "$REUSABLE_WORKFLOW"; then
  echo "Reusable deploy workflow must not use sh -lc for the remote deploy command." >&2
  exit 1
fi

remote_output="$(
  env -i PATH="/usr/bin:/bin" \
    sh -c "sh -c 'printf \"argc=%s arg1=%s\\n\" \"\$#\" \"\$1\"' deploy 'shiny-pelican'"
)"

if [ "$remote_output" != 'argc=1 arg1=shiny-pelican' ]; then
  echo "Reusable deploy workflow remote command must pass exactly one repository argument." >&2
  exit 1
fi

quote_remote_word() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

quoted_repo_name="$(quote_remote_word "shiny' pelican; echo bad")"
quoted_remote_output="$(
  env -i PATH="/usr/bin:/bin" \
    sh -c "sh -c 'printf \"argc=%s arg1=%s\\n\" \"\$#\" \"\$1\"' deploy $quoted_repo_name"
)"

if [ "$quoted_remote_output" != "argc=1 arg1=shiny' pelican; echo bad" ]; then
  echo "Reusable deploy workflow remote repository-name quoting must preserve one argument." >&2
  exit 1
fi

echo "tests/deploy-main-workflow.sh: deploy-main workflows verified."
