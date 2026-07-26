#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL="$REPO_ROOT/.agents/skills/secpal-pr-review/SKILL.md"
CONTRACT="$REPO_ROOT/.agents/skills/secpal-pr-review/references/contract.md"
EVIDENCE="$REPO_ROOT/scripts/secpal-pr-review.py"
ACTIONS="$REPO_ROOT/scripts/secpal-pr-review-actions.py"
REGISTRY="$REPO_ROOT/.agents/skills/secpal-pr-review/references/repositories.json"
PLAN_SCHEMA="$REPO_ROOT/.agents/skills/secpal-pr-review/references/mutation-plan.schema.json"
FAST_SCHEMA="$REPO_ROOT/.agents/skills/secpal-pr-review/references/fast-path-batch.schema.json"
FAST_PATH="$REPO_ROOT/scripts/secpal_pr_review/fast_path.py"
SIMPLE_RESOLVER="$REPO_ROOT/scripts/secpal-resolve-fixed-threads.py"
STATIC_POLICY="$REPO_ROOT/tests/secpal-pr-review-static-policy.py"
POLYSCOPE_TEMPLATE="$REPO_ROOT/templates/polyscope-codex-AGENTS.md"
WORKFLOW_DOC="$REPO_ROOT/docs/secpal-pr-review-workflow.md"
SIMPLE_RESOLUTION_DOC="$REPO_ROOT/docs/simple-pr-thread-resolution.md"
SCRIPT_README="$REPO_ROOT/scripts/README.md"
POLYSCOPE_INSTALLER="$REPO_ROOT/scripts/install-polyscope-rollout.sh"
INTEGRATION="$REPO_ROOT/tests/secpal-pr-review-skill-integration.sh"
QUALITY_WORKFLOW="$REPO_ROOT/.github/workflows/quality.yml"
GOVERNANCE_SUITE="$REPO_ROOT/tests/review-governance-suite.sh"
P21_BASELINE="833eef2afc063ae777e7e2b64b2f252e3fe1e49e"

fail() {
  printf 'policy failure: %s\n' "$1" >&2
  exit 1
}

for required in \
  "$SKILL" \
  "$CONTRACT" \
  "$EVIDENCE" \
  "$ACTIONS" \
  "$FAST_PATH" \
  "$SIMPLE_RESOLVER" \
  "$STATIC_POLICY" \
  "$POLYSCOPE_TEMPLATE" \
  "$WORKFLOW_DOC" \
  "$SIMPLE_RESOLUTION_DOC" \
  "$SCRIPT_README" \
  "$POLYSCOPE_INSTALLER" \
  "$REGISTRY" \
  "$PLAN_SCHEMA" \
  "$FAST_SCHEMA"; do
  test -f "$required" || fail "missing ${required#"$REPO_ROOT"/}"
done
test -x "$GOVERNANCE_SUITE" || fail 'registered governance suite is not executable'

# Policy cases: exact fast-path counters, one audit, explicit checkpoint, one
# bounded read retry, no polling, and zero review-request/merge authority.
grep -Fq 'normal_complete_snapshots: 0' "$CONTRACT" || fail 'normal snapshot limit drifted'
grep -Fq 'normal_stable_feedback_reads: 1' "$CONTRACT" || fail 'stable feedback read limit drifted'
grep -Fq 'normal_required_check_reads_before_resolution: 0' "$CONTRACT" || fail 'default remediation still reads Required Checks'
grep -Fq 'normal_complete_validation_runs: 1' "$CONTRACT" || fail 'complete validation limit drifted'
grep -Fq 'maximum_holistic_audits: 1' "$CONTRACT" || fail 'holistic audit limit drifted'
grep -Fq 'normal_signed_remediation_commits: 1' "$CONTRACT" || fail 'commit limit drifted'
grep -Fq 'normal_fast_forward_pushes: 1' "$CONTRACT" || fail 'push limit drifted'
grep -Fq 'maximum_evidence_replies_total: 10' "$CONTRACT" || fail 'reply limit drifted'
grep -Fq 'WAIT_FOR_EXPLICIT_USER_MERGE_AUTHORIZATION' "$CONTRACT" || fail 'user checkpoint missing'
grep -Fq 'A normal invocation has one remediation pass.' "$CONTRACT" || fail 'single-pass rule missing'
grep -Fq 'never appends unreviewed feedback' "$CONTRACT" || fail 'late-feedback rule missing'

template_text="$(tr '\n' ' ' <"$POLYSCOPE_TEMPLATE" | tr -s '[:space:]' ' ')"
grep -Fq \
  'Do not read, monitor, poll, wait for, summarize, or gate work on GitHub-hosted CI unless the user explicitly requests CI inspection, check status, merge readiness, or merge authorization in the current instruction.' \
  <<<"$template_text" \
  || fail 'Polyscope hosted-CI authorization rule is missing'
grep -Fq \
  'A previous request, repository convention, push, PR creation, review-remediation request, or thread-resolution request is not sufficient authorization.' \
  <<<"$template_text" \
  || fail 'Polyscope hosted-CI authorization cannot be inherited'
grep -Fq 'Local push hooks and local validation remain allowed.' <<<"$template_text" \
  || fail 'Polyscope runtime no longer permits local validation and push hooks'
grep -Fq 'They remain required where repository instructions require them.' <<<"$template_text" \
  || fail 'Polyscope runtime no longer requires configured local validation and hooks'
grep -Fq 'A push never authorizes hosted-CI inspection.' <<<"$template_text" \
  || fail 'push incorrectly implies hosted-CI authorization'
grep -Fq 'Draft PR creation never authorizes hosted-CI inspection.' <<<"$template_text" \
  || fail 'Draft PR creation incorrectly implies hosted-CI authorization'
grep -Fq 'verify its number, base, head branch, and head SHA, report local validation, and stop' <<<"$template_text" \
  || fail 'Draft PR terminal behavior is not CI-isolated'
grep -Fq 'Resolution of fixed review comments is independent of GitHub-hosted CI.' <<<"$template_text" \
  || fail 'fixed-comment resolution is still coupled to hosted CI'
grep -Fq 'Push and PR creation never imply CI-observation authorization.' <<<"$template_text" \
  || fail 'push and PR creation authorization boundary is missing'
grep -F 'CODEX_AGENTS_SOURCE=' "$POLYSCOPE_INSTALLER" \
  | grep -Fq 'templates' \
  || fail 'Polyscope rollout no longer sources the repository template'
grep -Fq "ln -sfn \"\$CODEX_AGENTS_SOURCE\" \"\$CODEX_AGENTS_TARGET\"" "$POLYSCOPE_INSTALLER" \
  || fail 'Polyscope rollout no longer installs the direct global instruction symlink'

normal_contract_state="$(
  sed -n '/^## Normal fast-path state machine$/,/^## /p' "$CONTRACT"
)"
test -n "$normal_contract_state" || fail 'normal remediation state machine is missing'
if grep -Fq 'READ_REQUIRED_CHECKS_ONCE' <<<"$normal_contract_state"; then
  fail 'default remediation state machine still reads Required Checks'
fi
grep -Fq 'RESOLVE_FIXED_THREADS' <<<"$normal_contract_state" \
  || fail 'default remediation does not resolve through the simple fixed-thread path'

readiness_contract="$(
  sed -n '/^## Explicit CI and readiness path$/,/^## /p' "$CONTRACT" \
    | tr '\n' ' ' \
    | tr -s '[:space:]' ' '
)"
test -n "$readiness_contract" || fail 'explicit CI/readiness path is missing'
grep -Fq 'current user instruction explicitly requests' <<<"$readiness_contract" \
  || fail 'CI/readiness authorization is not bound to the current instruction'
grep -Fq 'at most one bounded current-state read' <<<"$readiness_contract" \
  || fail 'explicit readiness path is not limited to one current-state read'
grep -Fq 'never polls, waits, sleeps, or repeats automatically' <<<"$readiness_contract" \
  || fail 'explicit readiness path permits monitoring behavior'

normal_skill_section="$(sed -n '/^## Run the finite invocation$/,/^## /p' "$SKILL")"
test -n "$normal_skill_section" || fail 'normal skill workflow is missing'
grep -Fq 'scripts/secpal-resolve-fixed-threads.py' <<<"$normal_skill_section" \
  || fail 'review remediation does not use the simple fixed-thread resolver'
if grep -Eq 'Required Checks|mergeability|branch-protection|pull-request reactions' <<<"$normal_skill_section"; then
  fail 'default remediation still gates resolution on unrelated readiness state'
fi

if grep -Eqi \
  'hosted checks are still running|wait (for|until) (CI|checks)|new invocation.*(CI|check|CodeQL)|CodeQL is still|thread cannot be resolved.*(PEST|check)' \
  "$POLYSCOPE_TEMPLATE" "$SKILL" "$WORKFLOW_DOC" "$SIMPLE_RESOLUTION_DOC" "$SCRIPT_README"; then
  fail 'default workflow text instructs CI waiting or a follow-up invocation'
fi

if grep -Fq 'required_ci_succeeded' "$ACTIONS"; then
  fail 'thread-resolution preconditions still require hosted CI'
fi
grep -Fq '"required_ci_succeeded"' "$PLAN_SCHEMA" \
  || fail 'version-1 forensic plans lost the optional Required Check compatibility field'
if jq -e \
  '.["$defs"].operation.properties.resolution_preconditions.required | index("required_ci_succeeded")' \
  "$PLAN_SCHEMA" >/dev/null; then
  fail 'legacy Required Check compatibility field became a resolution precondition again'
fi
grep -Fq -- '--reviewed-state REVIEWED_STATE' "$SIMPLE_RESOLUTION_DOC" \
  || fail 'simple resolver documentation does not bind mutations to reviewed feedback'
grep -Fq 'When remediation changes no tracked source file' "$CONTRACT" \
  || fail 'normal remediation lost the no-change resolution path'
grep -Fq 'skip the commit and push states' "$SKILL" \
  || fail 'skill still forces an artificial remediation commit'

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

prohibited_authority_pattern='gh[[:space:]]+pr[[:space:]]+(review|ready|merge)|requestReviews|enablePullRequestAutoMerge|mergePullRequest|addLabelsToLabelable|createIssue'

if grep -En 'retrying' "$ACTIONS" "$FAST_PATH" "$SIMPLE_RESOLVER"; then
  fail 'mutation helper contains polling behavior'
fi
if grep -En "$prohibited_authority_pattern" "$ACTIONS" "$FAST_PATH" "$SIMPLE_RESOLVER"; then
  fail 'mutation helper exposes prohibited GitHub authority'
fi

python3 \
  "$STATIC_POLICY" \
  "$EVIDENCE" \
  "$ACTIONS" \
  "$FAST_PATH" \
  "$SIMPLE_RESOLVER"

grep -Eq "$prohibited_authority_pattern" <<< 'mergePullRequest' \
  || fail 'authority policy negative fixture was not detected'

grep -Fq 'secpal-pr-review.py' "$SKILL" || fail 'skill does not route reads through P2.1 helper'
grep -Fq 'secpal-pr-review-actions.py' "$SKILL" || fail 'skill does not route bounded writes through action helper'
grep -Fq 'explicit PR-feedback remediation request' "$SKILL" || fail 'skill trigger is not narrow'
sed -n '/^description:/p' "$SKILL" \
  | grep -Fq 'fixed-thread resolution-only requests' \
  || fail 'skill trigger does not advertise fixed-thread resolution-only requests'
grep -Fq 'not a reviewer' "$SKILL" || fail 'skill reviewer boundary is missing'
simple_skill_section="$(sed -n '/^## Simple fixed-thread resolution$/,/^## /p' "$SKILL")"
test -n "$simple_skill_section" || fail 'skill simple-resolution route is missing'
grep -Fq 'scripts/secpal-resolve-fixed-threads.py' <<<"$simple_skill_section" \
  || fail 'skill does not route fixed-and-pushed requests through the simple resolver'
grep -Fq -- '--apply' <<<"$simple_skill_section" \
  || fail 'skill fixed-thread resolution route does not require apply mode'
if grep -Fq 'resolve-batch' <<<"$simple_skill_section"; then
  fail 'skill simple-resolution route still invokes the readiness batch'
fi
grep -Fq 'Simple resolution-only path' "$CONTRACT" \
  || fail 'contract does not define the simple resolution-only path'
grep -Fq 'scripts/secpal-resolve-fixed-threads.py' "$CONTRACT" \
  || fail 'contract does not bind the simple resolver'
grep -Fq 'expected current head OID' "$SIMPLE_RESOLUTION_DOC" \
  || fail 'simple resolver documentation is not head-bound'
grep -Fq 'every requested thread belongs to that PR' "$SIMPLE_RESOLUTION_DOC" \
  || fail 'simple resolver documentation is not target-bound'

git -C "$REPO_ROOT" cat-file -e "$P21_BASELINE^{commit}" 2>/dev/null \
  || fail "accepted P2.1 baseline commit is unavailable: $P21_BASELINE"
cmp "$EVIDENCE" <(git -C "$REPO_ROOT" show "$P21_BASELINE:scripts/secpal-pr-review.py") \
  || fail 'accepted P2.1 evidence helper changed'

test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yml" || fail 'skill must not run automatically'
test ! -e "$REPO_ROOT/.github/workflows/secpal-pr-review.yaml" || fail 'skill must not run automatically'
if grep -En '/home/secpal' "$INTEGRATION"; then
  fail 'integration test must not depend on one host account layout'
fi
grep -Fq 'python3 -m unittest tests/secpal-pr-review-actions-unit.py' "$QUALITY_WORKFLOW" \
  || fail 'guarded-action unit tests are not enforced in CI'
grep -Fq 'python3 -m unittest tests/secpal-resolve-fixed-threads-unit.py' "$QUALITY_WORKFLOW" \
  || fail 'simple resolver unit tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-policy.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill policy tests are not enforced in CI'
grep -Fq 'bash tests/secpal-pr-review-skill-integration.sh' "$QUALITY_WORKFLOW" \
  || fail 'skill integration tests are not enforced in CI'
grep -Fq './tests/review-governance-suite.sh' "$REGISTRY" \
  || fail 'repository governance suite is not registered'
grep -Fq 'tests/secpal-resolve-fixed-threads-unit.py' "$REGISTRY" \
  || fail 'simple resolver unit tests are not registered'

protected_paths=(
  "$REPO_ROOT"/.github/workflows/*-review-memory.yml
  "$REPO_ROOT"/scripts/*-review-tool.sh
  "$REPO_ROOT"/docs/*-review-automation.md
  "$REPO_ROOT"/AGENTS.md
)
relative_paths=()
for path in "${protected_paths[@]}"; do
  relative_paths+=("${path#"$REPO_ROOT"/}")
done
test "$(git -C "$REPO_ROOT" diff --name-only "$P21_BASELINE" -- "${relative_paths[@]}" | wc -l)" -eq 0 \
  || fail 'existing review governance or instruction routing changed'

python3 - "$PLAN_SCHEMA" "$FAST_SCHEMA" "$REGISTRY" <<'PY'
import json
import sys

plan_schema = json.load(open(sys.argv[1], encoding="utf-8"))
fast_schema = json.load(open(sys.argv[2], encoding="utf-8"))
registry = json.load(open(sys.argv[3], encoding="utf-8"))

allowed = {"REACTION", "EVIDENCE_REPLY", "THREAD_RESOLUTION"}
operation_kind = plan_schema["$defs"]["operation"]["properties"]["kind"]["enum"]
assert set(operation_kind) == allowed
serialized = json.dumps(plan_schema, sort_keys=True)
for prohibited in (
    "REVIEW_REQUEST", "READY_TRANSITION", "LABEL", "ISSUE", "REVIEW_SUBMISSION",
    "MERGE", "AUTO_MERGE", "COMMENT_DELETE", "REVIEW_DISMISSAL", "BRANCH_WRITE",
):
    assert f'"{prohibited}"' not in serialized
    assert f'"{prohibited}"' not in json.dumps(fast_schema, sort_keys=True)
assert fast_schema["$defs"]["operation"]["properties"]["kind"] == {
    "const": "THREAD_RESOLUTION"
}

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
