#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression checks for the Copilot review memory workflow privilege boundary.
# pull_request_review events can be triggered by pull requests whose head tree
# is attacker-controlled, so any local code run after minting the GitHub App
# token must come from the trusted base commit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/copilot-review-memory.yml"
TRUSTED_REVIEW_REF='          ref: ${{ github.event_name == '\''pull_request_review'\'' && github.event.pull_request.base.sha || github.sha }}'

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

grep -q '^  pull_request_review:$' "$WORKFLOW" || {
  echo "Copilot review memory workflow must keep the pull_request_review trigger under regression coverage." >&2
  exit 1
}

grep -q '^        uses: actions/create-github-app-token@v3$' "$WORKFLOW" || {
  echo "Copilot review memory workflow must keep the GitHub App token step under regression coverage." >&2
  exit 1
}

# The privileged job runs local repository scripts with GH_TOKEN set to the App
# token. Guard against regressing to the default checkout for review events,
# where the script path can be supplied by the pull request head tree.
checkout_line=$(grep -n '^      - name: Checkout repository$' "$WORKFLOW" | cut -d: -f1 | head -n1)
first_script_line=$(grep -n '^          ./scripts/copilot-review-tool\.sh scan \\$' "$WORKFLOW" | cut -d: -f1 | head -n1)
if [ -z "$checkout_line" ] || [ -z "$first_script_line" ] || [ "$checkout_line" -ge "$first_script_line" ]; then
  echo "Copilot review memory workflow must checkout trusted code before running copilot-review-tool.sh." >&2
  exit 1
fi

if awk -v start="$checkout_line" -v trusted_ref="$TRUSTED_REVIEW_REF" '
  NR == start { in_checkout = 1; next }
  in_checkout && /^      - name:/ { in_checkout = 0 }
  in_checkout && /^        with:/ { has_with = 1 }
  in_checkout && $0 == trusted_ref { has_trusted_ref = 1 }
  END { exit !(has_with && has_trusted_ref) }
' "$WORKFLOW"; then
  :
else
  echo "Checkout before privileged local script execution must include the trusted pull_request_review base SHA ref." >&2
  exit 1
fi

echo "✓ copilot review memory workflow privilege-boundary checks passed"
