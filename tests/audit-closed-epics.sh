#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/audit-closed-epics.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/bin" "$workspace/fixtures"

cat >"$workspace/bin/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

fixture_dir="${EPIC_AUDIT_FIXTURE_DIR:?}"

if [ "$1" != "api" ]; then
  echo "unexpected gh command: $*" >&2
  exit 1
fi

shift

if [ "$1" = "/search/issues" ]; then
  cat "$fixture_dir/search.json"
  exit 0
fi

case "$1" in
  /repos/SecPal/api/issues/10)
    cat "$fixture_dir/api-10.json"
    ;;
  /repos/SecPal/frontend/issues/30)
    cat "$fixture_dir/frontend-30.json"
    ;;
  /repos/SecPal/.github/issues/40)
    cat "$fixture_dir/github-40.json"
    ;;
  *)
    echo "unexpected gh api endpoint: $1" >&2
    exit 1
    ;;
esac
STUB
chmod +x "$workspace/bin/gh"

cat >"$workspace/fixtures/search.json" <<'JSON'
{
  "total_count": 1,
  "incomplete_results": false,
  "items": [
    {
      "number": 500,
      "title": "[EPIC] Demo epic",
      "body": "- [x] SecPal/api#10 -> [PR #20](https://github.com/SecPal/api/pull/20)\n- [ ] SecPal/frontend#30 - stale checklist item\n- [ ] #40 - still open child issue",
      "repository_url": "https://api.github.com/repos/SecPal/.github"
    }
  ]
}
JSON

cat >"$workspace/fixtures/api-10.json" <<'JSON'
{
  "state": "closed",
  "title": "Closed child"
}
JSON

cat >"$workspace/fixtures/frontend-30.json" <<'JSON'
{
  "state": "closed",
  "title": "Closed child with stale epic checklist"
}
JSON

cat >"$workspace/fixtures/github-40.json" <<'JSON'
{
  "state": "open",
  "title": "Open child issue"
}
JSON

output_file="$workspace/output.txt"

set +e
PATH="$workspace/bin:$PATH" \
EPIC_AUDIT_FIXTURE_DIR="$workspace/fixtures" \
bash "$REPO_ROOT/scripts/audit-closed-epics.sh" --org SecPal --repo .github >"$output_file" 2>&1
exit_code=$?
set -e

if [ "$exit_code" -ne 1 ]; then
  cat "$output_file"
  echo "audit-closed-epics.sh exited with $exit_code; expected 1" >&2
  exit 1
fi

grep -q 'SecPal/frontend#30 is closed but still unchecked' "$output_file"
grep -q 'SecPal/.github#40 is still open' "$output_file"

# SecPal/api#10 is a valid checked and closed checklist item and must not be reported.
if grep -q 'SecPal/api#10' "$output_file"; then
  cat "$output_file"
  echo "audit-closed-epics.sh incorrectly flagged a valid checked-and-closed issue" >&2
  exit 1
fi

if grep -q '#20' "$output_file"; then
  cat "$output_file"
  echo "audit-closed-epics.sh incorrectly treated a PR reference as an issue" >&2
  exit 1
fi
