#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HELPER="$REPO_ROOT/scripts/secpal-pr-review.py"
FIXTURES="$SCRIPT_DIR/fixtures/secpal-pr-review"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/secpal-pr-review-integration.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/bin" "$workspace/output"
cp "$FIXTURES/fake-gh.py" "$workspace/bin/gh"
cp "$FIXTURES/fake-git.py" "$workspace/bin/git"
chmod 0700 "$workspace/bin/gh" "$workspace/bin/git"

export PATH="$workspace/bin:$PATH"
export FAKE_GH_FIXTURE="$FIXTURES/fake-github-pages.json"
export FAKE_GH_LOG="$workspace/gh.log"
export FAKE_GIT_LOG="$workspace/git.log"

first="$workspace/first.json"
second="$workspace/second.json"
markdown="$workspace/output/snapshot.md"
json_output="$workspace/output/snapshot.json"

python3 "$HELPER" snapshot \
  --repo SecPal/.github \
  --pr 1 \
  --config "$FIXTURES/config.json" >"$first"

python3 "$HELPER" snapshot \
  --repo SecPal/.github \
  --pr 1 \
  --config "$FIXTURES/config.json" >"$second"

cmp "$first" "$second"

python3 "$HELPER" verify-gate \
  --snapshot "$first" \
  --config "$FIXTURES/config.json" >"$workspace/gate.json"

python3 "$HELPER" verify-local \
  --repo SecPal/.github \
  --pr 1 \
  --config "$FIXTURES/config.json" \
  --expected-head aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa >"$workspace/local.json"

python3 "$HELPER" render --snapshot "$first" --format markdown >"$workspace/rendered.md"
grep -Fq 'Canonical authority: JSON snapshot and SHA-256 digest' "$workspace/rendered.md"

python3 "$HELPER" snapshot \
  --repo SecPal/.github \
  --pr 1 \
  --config "$FIXTURES/config.json" \
  --output "$json_output" \
  --markdown-output "$markdown" >"$workspace/output-message.json"

test "$(stat -c '%a' "$json_output")" = "600"
test "$(stat -c '%a' "$markdown")" = "600"
cmp "$first" "$json_output"

python3 - "$first" "$workspace/gate.json" "$workspace/local.json" <<'PY'
import hashlib
import json
import sys

snapshot_path, gate_path, local_path = sys.argv[1:]
snapshot = json.load(open(snapshot_path, encoding="utf-8"))
provided = snapshot.pop("snapshot_digest")
canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
assert hashlib.sha256(canonical).hexdigest() == provided

gate = json.load(open(gate_path, encoding="utf-8"))
assert gate["raw_review_state"]["reviews"] == 2
assert gate["raw_review_state"]["conversation_comments"] == 1
assert gate["raw_review_state"]["review_threads"] == 2
assert gate["raw_review_state"]["unresolved_threads"] == 0
assert gate["technical_classification_required"] is True

assert len(snapshot["conversation_comments"][0]["reactions"]) == 2
assert len(snapshot["review_threads"][0]["comments"]) == 2
assert snapshot["review_threads"][1]["is_outdated"] is True
connections = {item["connection"]: item for item in snapshot["completeness"]["fully_paginated_connections"]}
assert connections["reviews"]["pages"] == 2
assert connections["review_threads"]["pages"] == 2
assert connections["review_thread.THREAD_1.comments"]["pages"] == 2
assert connections["conversation_comment.ISSUE_COMMENT_1.reactions"]["pages"] == 2
assert connections["checks"]["pages"] == 2

local = json.load(open(local_path, encoding="utf-8"))
assert local["blockers"] == []
assert local["local_head"] == "a" * 40
PY

python3 - "$workspace/gh.log" "$workspace/git.log" <<'PY'
import json
import sys

gh_log, git_log = sys.argv[1:]
gh_calls = [json.loads(line) for line in open(gh_log, encoding="utf-8")]
git_calls = [json.loads(line) for line in open(git_log, encoding="utf-8")]

assert gh_calls
assert git_calls
for call in gh_calls:
    assert call[0] == "api", call
    if "--method" in call:
        assert call[call.index("--method") + 1] == "GET", call
    query = next((arg.split("=", 1)[1] for arg in call if arg.startswith("query=")), "")
    assert "mutation" not in query.lower(), call

prohibited_git = {"push", "commit", "checkout", "switch", "reset", "clean", "stash", "fetch"}
assert all(not call or call[0] not in prohibited_git for call in git_calls)
PY

if grep -Eiq '(^|[^[:alnum:]_])(mutation|POST|PUT|PATCH|DELETE)([^[:alnum:]_]|$)' "$workspace/gh.log"; then
  echo "Fake gh observed a prohibited GitHub mutation operation." >&2
  exit 1
fi

printf '✓ deterministic PR evidence integration checks passed\n'
