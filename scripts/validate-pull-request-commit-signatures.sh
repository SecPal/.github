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
  temporary_payload="$(mktemp "${TMPDIR:-/tmp}/pull-request-commits.json.XXXXXX")"
  printf '%s' "$PR_COMMITS_JSON" > "$temporary_payload"
  payload_file="$temporary_payload"
fi

if [ -z "$payload_file" ] || [ ! -f "$payload_file" ] || [ ! -s "$payload_file" ]; then
  echo 'Pull request commit payload is required.' >&2
  exit 1
fi

python_command=''

if command -v python3 >/dev/null 2>&1; then
  python_command='python3'
elif command -v python >/dev/null 2>&1 && python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info.major == 3 else 1)
PY
then
  python_command='python'
fi

if command -v node >/dev/null 2>&1; then
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
  exit 0
fi

if [ -n "$python_command" ]; then
  "$python_command" - "$payload_file" <<'PY'
import json
import sys

payload_path = sys.argv[1]

try:
  with open(payload_path, 'r', encoding='utf-8') as payload_file_handle:
    commits = json.load(payload_file_handle)
except Exception:
  print('Invalid pull request commit payload.', file=sys.stderr)
  raise SystemExit(1)

if not isinstance(commits, list):
  print('Invalid pull request commit payload.', file=sys.stderr)
  raise SystemExit(1)

flattened_commits = []
for entry in commits:
  if isinstance(entry, list):
    flattened_commits.extend(entry)
  else:
    flattened_commits.append(entry)

if len(flattened_commits) == 0:
  print('No commits found in pull request payload.', file=sys.stderr)
  raise SystemExit(1)

failures = []

for entry in flattened_commits:
  commit = entry.get('commit') if isinstance(entry, dict) else None
  verification = commit.get('verification') if isinstance(commit, dict) else None
  sha = str(entry.get('sha', 'unknown')) if isinstance(entry, dict) else 'unknown'
  verified = isinstance(verification, dict) and verification.get('verified') is True
  reason = str(verification.get('reason', 'missing')) if isinstance(verification, dict) else 'missing'
  message = ''
  if isinstance(commit, dict):
    message = str(commit.get('message', ''))
  message = message.split('\n', 1)[0]

  if not verified:
    failures.append({'sha': sha, 'reason': reason, 'message': message})

if len(failures) == 0:
  raise SystemExit(0)

print('Unsigned or unverified commits were found in this pull request:', file=sys.stderr)
for failure in failures:
  print(
    f"- {failure['sha']} reason={failure['reason']} message={failure['message']}",
    file=sys.stderr,
  )
print('All commits in a pull request must be GitHub-verified signed commits.', file=sys.stderr)
raise SystemExit(1)
PY
  exit 0
fi

echo 'Node.js or Python 3 is required to validate pull request commit signatures.' >&2
exit 1
