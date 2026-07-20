#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL="$REPO_ROOT/.agents/skills/secpal-pr-review/SKILL.md"
CONTRACT="$REPO_ROOT/.agents/skills/secpal-pr-review/references/contract.md"
ACTIONS="$REPO_ROOT/scripts/secpal-pr-review-actions.py"
EVIDENCE="$REPO_ROOT/scripts/secpal-pr-review.py"
REGISTRY="$REPO_ROOT/.agents/skills/secpal-pr-review/references/repositories.json"
PLAN_SCHEMA="$REPO_ROOT/.agents/skills/secpal-pr-review/references/mutation-plan.schema.json"
INTEGRATION="$REPO_ROOT/tests/secpal-pr-review-skill-integration.sh"
QUALITY_WORKFLOW="$REPO_ROOT/.github/workflows/quality.yml"
MEMORY_ERRORS="$REPO_ROOT/tests/copilot-review-memory-errors.sh"
P21_BASELINE="833eef2afc063ae777e7e2b64b2f252e3fe1e49e"

fail() {
  printf 'policy failure: %s\n' "$1" >&2
  exit 1
}

command -v rg >/dev/null 2>&1 || fail 'ripgrep (rg) is required'

for required in "$SKILL" "$CONTRACT" "$ACTIONS" "$REGISTRY" "$PLAN_SCHEMA"; do
  test -f "$required" || fail "missing ${required#"$REPO_ROOT"/}"
done
test -x "$MEMORY_ERRORS" || fail 'registered review-memory error test is not executable'

# Policy cases: exact finite counters, one audit, explicit checkpoint, no third
# cycle, no polling/retry, no automatic late-feedback incorporation, and zero
# review-request/merge authority.
grep -Fq 'maximum_remediation_cycles: 2' "$CONTRACT" || fail 'maximum remediation cycles drifted'
grep -Fq 'maximum_logical_github_state_captures: 3' "$CONTRACT" || fail 'state capture limit drifted'
grep -Fq 'maximum_holistic_audits: 1' "$CONTRACT" || fail 'holistic audit limit drifted'
grep -Fq 'maximum_signed_remediation_commits: 2' "$CONTRACT" || fail 'commit limit drifted'
grep -Fq 'maximum_fast_forward_pushes: 2' "$CONTRACT" || fail 'push limit drifted'
grep -Fq 'maximum_evidence_replies_total: 10' "$CONTRACT" || fail 'reply limit drifted'
grep -Fq 'WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION' "$CONTRACT" || fail 'user checkpoint missing'
grep -Fq 'A third remediation cycle is prohibited.' "$CONTRACT" || fail 'third-cycle prohibition missing'
grep -Fq 'Late feedback requires a fresh explicit user invocation' "$CONTRACT" || fail 'late-feedback rule missing'

for phrase in \
  'zero review requests' \
  'zero Draft-to-Ready transitions' \
  'zero merge operations' \
  'zero auto-merge operations' \
  'no polling' \
  'no sleep-and-retry' \
  'Green CI does not establish technical truth'; do
  grep -Fqi "$phrase" "$CONTRACT" || fail "missing contract phrase: $phrase"
done

if rg -n 'sleep\(|time\.sleep|while[[:space:]]+true|for[[:space:]].*retry|retrying' "$ACTIONS"; then
  fail 'mutation helper contains polling or retry behavior'
fi

if rg -n 'gh[[:space:]]+pr[[:space:]]+(review|ready|merge)|requestReviews|enablePullRequestAutoMerge|mergePullRequest|addLabelsToLabelable|createIssue' "$ACTIONS"; then
  fail 'mutation helper exposes prohibited GitHub authority'
fi

if rg -n 'subprocess\.(run|Popen).*shell[[:space:]]*=[[:space:]]*True|\beval\(' "$ACTIONS"; then
  fail 'mutation helper permits shell execution'
fi

grep -Fq 'secpal-pr-review.py' "$SKILL" || fail 'skill does not route reads through P2.1 helper'
grep -Fq 'secpal-pr-review-actions.py' "$SKILL" || fail 'skill does not route bounded writes through action helper'
grep -Fq 'explicit PR-feedback remediation request' "$SKILL" || fail 'skill trigger is not narrow'
grep -Fq 'not a reviewer' "$SKILL" || fail 'skill reviewer boundary is missing'

git -C "$REPO_ROOT" cat-file -e "$P21_BASELINE^{commit}" 2>/dev/null \
  || fail "accepted P2.1 baseline commit is unavailable: $P21_BASELINE"
cmp "$EVIDENCE" <(git -C "$REPO_ROOT" show "$P21_BASELINE:scripts/secpal-pr-review.py") \
  || fail 'accepted P2.1 evidence helper changed'

test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yml" || fail 'skill must not run automatically'
test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yaml" || fail 'skill must not run automatically'
if rg -n '/home/secpal' "$INTEGRATION"; then
  fail 'integration test must not depend on one host account layout'
fi
grep -Fq 'python3 -m unittest tests/secpal-pr-review-actions-unit.py' "$QUALITY_WORKFLOW" \
  || fail 'guarded-action unit tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-policy.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill policy tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-integration.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill integration tests are not enforced in CI'
test "$(git -C "$REPO_ROOT" diff --name-only 833eef2afc063ae777e7e2b64b2f252e3fe1e49e -- .github/workflows/copilot-review-memory.yml scripts/copilot-review-tool.sh docs/copilot-review-automation.md | wc -l)" -eq 0 \
  || fail 'review-memory files changed'
test "$(git -C "$REPO_ROOT" diff --name-only 833eef2afc063ae777e7e2b64b2f252e3fe1e49e -- AGENTS.md templates/polyscope-codex-AGENTS.md | wc -l)" -eq 0 \
  || fail 'global AGENTS routing source changed'

python3 - "$PLAN_SCHEMA" "$REGISTRY" <<'PY'
import json
import sys

plan_schema = json.load(open(sys.argv[1], encoding="utf-8"))
registry = json.load(open(sys.argv[2], encoding="utf-8"))

allowed = {"REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION"}
operation_kind = plan_schema["$defs"]["operation"]["properties"]["kind"]["enum"]
assert set(operation_kind) == allowed
serialized = json.dumps(plan_schema, sort_keys=True)
for prohibited in (
    "REVIEW_REQUEST", "READY_TRANSITION", "LABEL", "ISSUE", "REVIEW_SUBMISSION",
    "MERGE", "AUTO_MERGE", "COMMENT_DELETE", "REVIEW_DISMISSAL", "BRANCH_WRITE",
):
    assert f'"{prohibited}"' not in serialized

expected = [
    "SecPal/.github", "SecPal/api", "SecPal/frontend", "SecPal/contracts",
    "SecPal/android", "SecPal/changelog", "SecPal/GuardGuide",
    "SecPal/guardguide.de", "SecPal/secpal.app",
]
assert [item["repository"] for item in registry["repositories"]] == expected
for item in registry["repositories"]:
    for command_group in ("focused_validation", "required_local_validation"):
        for command in item[command_group]:
            assert isinstance(command["argv"], list)
            assert command["argv"]
            assert all(isinstance(value, str) and value for value in command["argv"])
PY

printf '✓ finite secpal-pr-review skill policy checks passed\n'
