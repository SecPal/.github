#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression checks for the Copilot review memory workflow privilege boundary.
# pull_request_review events can be triggered by pull requests whose head tree
# is attacker-controlled, so any local code run after minting the GitHub App
# token must come from the current trusted base ref.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/copilot-review-memory.yml"
# shellcheck disable=SC2016
# Literal GitHub expression expected in workflow YAML.
TRUSTED_REVIEW_REF='          ref: ${{ github.event_name == '\''pull_request_review'\'' && github.event.pull_request.base.ref || github.sha }}'

first_line_number() {
  local pattern="$1"
  local match

  match="$(grep -n -m1 "$pattern" "$WORKFLOW" || true)"
  if [ -z "$match" ]; then
    return 1
  fi

  printf '%s\n' "${match%%:*}"
}

if [ ! -f "$WORKFLOW" ]; then
  echo "Expected workflow was not found: $WORKFLOW" >&2
  exit 1
fi

grep -q '^  pull_request_review:$' "$WORKFLOW" || {
  echo "Copilot review memory workflow must keep the pull_request_review trigger under regression coverage." >&2
  exit 1
}

grep -qE '^        uses: actions/create-github-app-token@[0-9a-f]{40}[[:space:]]+#[[:space:]]+v3\.2\.0$' "$WORKFLOW" || {
  echo "Copilot review memory workflow must keep the GitHub App token step under regression coverage." >&2
  exit 1
}

# The privileged job runs local repository scripts with GH_TOKEN set to the App
# token. Guard against regressing to the default checkout for review events,
# where the script path can be supplied by the pull request head tree.
checkout_line="$(first_line_number '^      - name: Checkout repository$' || true)"
first_script_line="$(first_line_number '^          ./scripts/copilot-review-tool\.sh scan \\$' || true)"
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
  echo "Checkout before privileged local script execution must include the current trusted pull_request_review base ref." >&2
  exit 1
fi

echo "✓ copilot review memory workflow privilege-boundary checks passed"

# Exercise the real CLI without credentials or a live GitHub boundary.
cli_workspace="$(mktemp -d "${TMPDIR:-/tmp}/copilot-review-memory.XXXXXX")"
trap 'rm -rf -- "$cli_workspace"' EXIT
mkdir -p "$cli_workspace/bin"
cat >"$cli_workspace/bin/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$GH_CALL_LOG"
case "$1 $2" in
  'api graphql')
    printf '%s\n' '{"data":{"repository":{"pullRequest":{"reviewThreads":{"pageInfo":{"hasNextPage":false},"nodes":[{"id":"PRRT_fixture","isResolved":false,"path":"fixture.sh","line":1,"comments":{"pageInfo":{"hasNextPage":false},"nodes":[{"author":{"login":"copilot-pull-request-reviewer"},"body":"Fixture finding.","url":"https://github.com/example/repository/pull/1#discussion_fixture"}]}}]}}}}}'
    ;;
  'pr list')
    printf '%s\n' '[{"number":1,"title":"Fixture PR","url":"https://github.com/example/repository/pull/1","isDraft":false}]'
    ;;
  *) exit 91 ;;
esac
EOF
chmod +x "$cli_workspace/bin/gh"

run_cli() {
  env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
    PATH="$cli_workspace/bin:$PATH" GH_CALL_LOG="$cli_workspace/gh.calls" \
    bash "$REPO_ROOT/scripts/copilot-review-tool.sh" "$@"
}

if run_cli resolve --thread-id PRRT_fixture >"$cli_workspace/resolve.log" 2>&1; then
  cat "$cli_workspace/gh.calls" >&2
  echo "Legacy raw resolution must reject the command before calling GitHub." >&2
  exit 1
fi
if [ -s "$cli_workspace/gh.calls" ]; then
  cat "$cli_workspace/gh.calls" >&2
  echo "Rejected legacy resolution must not attempt a GitHub call." >&2
  exit 1
fi
grep -Fq 'Unknown subcommand: resolve' "$cli_workspace/resolve.log" || {
  cat "$cli_workspace/resolve.log" >&2
  echo "Resolution rejection must come from command removal, not a tooling failure." >&2
  exit 1
}
run_cli --help >"$cli_workspace/help.log"
if grep -Fq 'resolve --thread-id' "$cli_workspace/help.log"; then
  echo "CLI help must not advertise raw thread resolution." >&2
  exit 1
fi
jq -e '.scripts | has("copilot:review:resolve") | not' "$REPO_ROOT/package.json" >/dev/null

run_cli threads --repo example/repository --pr 1 --format json >"$cli_workspace/threads.json"
jq -e 'length == 1 and .[0].id == "PRRT_fixture"' "$cli_workspace/threads.json" >/dev/null
run_cli lessons --repo example/repository --pr 1 >"$cli_workspace/lessons.md"
grep -Fq 'Finding: Fixture finding.' "$cli_workspace/lessons.md"
run_cli scan --repo example/repository --max-prs 1 \
  --output-dir "$cli_workspace/scan" >"$cli_workspace/scan.log"
grep -Fq 'Matching threads: 1' "$cli_workspace/scan/summary.md"
if grep -Fq 'mutation(' "$cli_workspace/gh.calls"; then
  echo "Read-only review tooling must not issue a GraphQL mutation." >&2
  exit 1
fi
echo "✓ legacy raw resolution rejected; read-only review CLI preserved"
