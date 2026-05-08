#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

payload_file="${PR_COMMITS_FILE:-}"
temporary_payload=''

cleanup() {
  if [ -n "$temporary_payload" ] && [ -f "$temporary_payload" ]; then
    rm -f "$temporary_payload"
  fi
}

trap cleanup EXIT

if [ -z "$payload_file" ] && [ -n "${PR_COMMITS_JSON:-}" ]; then
  temporary_payload="$(mktemp "${TMPDIR:-/tmp}/pull-request-commits.XXXXXX")"
  printf '%s' "$PR_COMMITS_JSON" > "$temporary_payload"
  payload_file="$temporary_payload"
fi

if [ -z "$payload_file" ] || [ ! -f "$payload_file" ] || [ ! -s "$payload_file" ]; then
  echo 'Pull request commit payload is required.' >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo 'Node.js is required to validate pull request commit signatures.' >&2
  exit 1
fi

node - "$payload_file" <<'NODE'
const fs = require('fs');

const payloadPath = process.argv[2];
let commits;

try {
  commits = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
} catch (error) {
  console.error('Invalid pull request commit payload.');
  process.exit(1);
}

if (!Array.isArray(commits)) {
  console.error('Invalid pull request commit payload.');
  process.exit(1);
}

commits = commits.flatMap((entry) => (Array.isArray(entry) ? entry : [entry]));

if (commits.length === 0) {
  console.error('No commits found in pull request payload.');
  process.exit(1);
}

const failures = commits
  .map((entry) => ({
    sha: String(entry?.sha ?? 'unknown'),
    verified: entry?.commit?.verification?.verified === true,
    reason: String(entry?.commit?.verification?.reason ?? 'missing'),
    message: String(entry?.commit?.message ?? '').split('\n')[0],
  }))
  .filter((entry) => !entry.verified);

if (failures.length === 0) {
  process.exit(0);
}

console.error('Unsigned or unverified commits were found in this pull request:');
for (const failure of failures) {
  console.error(`- ${failure.sha} reason=${failure.reason} message=${failure.message}`);
}
console.error('All commits in a pull request must be GitHub-verified signed commits.');
process.exit(1);
NODE
