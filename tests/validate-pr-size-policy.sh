#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
validator="$repo_root/scripts/validate-pr-size-policy.sh"
preflight="$repo_root/scripts/preflight.sh"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/validate-pr-size-policy.XXXXXX")"
trap 'rm -rf -- "$workspace"' EXIT

make_repo() {
  local name="$1"
  mkdir -p "$workspace/$name/scripts" "$workspace/$name/.github/workflows"
}

make_repo advisory
cat >"$workspace/advisory/scripts/preflight.sh" <<'EOF'
ADVISORY_THRESHOLD=600
CHANGED=$((INSERTIONS + DELETIONS))
echo "PR size: $CHANGED changed lines ($INSERTIONS insertions, $DELETIONS deletions; advisory threshold: $ADVISORY_THRESHOLD)"
if [ "$CHANGED" -gt "$ADVISORY_THRESHOLD" ]; then
  echo "WARNING: PR size advisory threshold exceeded."
fi
EOF
cat >"$workspace/advisory/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  pr-size:
    uses: SecPal/.github/.github/workflows/reusable-pr-size.yml@7f5d24a599c03cdc59998c22578c345c518b755d
EOF

make_repo no-gate
cat >"$workspace/no-gate/CHANGELOG.md" <<'EOF'
# Changelog

In 2025 the repository used a hard 600-line limit.
EOF

make_repo hard-exit
cat >"$workspace/hard-exit/scripts/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then
  echo "PR TOO LARGE"
  exit 2
fi
EOF

make_repo override-file
cat >"$workspace/override-file/scripts/preflight.sh" <<'EOF'
if [ -f .preflight-allow-large-pr ]; then
  echo "override active"
fi
EOF

make_repo label-override
cat >"$workspace/label-override/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: gh pr view "$PR_NUMBER" --json labels
      - run: grep -q large-pr-approved labels.json
EOF

make_repo workflow-failure
cat >"$workspace/workflow-failure/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: |
          if [ "$CHANGED" -gt "$MAX_LINES" ]; then
            echo "Maximum allowed: 600"
            exit 1
          fi
EOF

make_repo exit-three
cat >"$workspace/exit-three/scripts/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then
  echo "PR exceeds the size limit"
  exit 3
fi
EOF

make_repo lowercase-variable
cat >"$workspace/lowercase-variable/scripts/preflight.sh" <<'EOF'
# This counter is derived from the PR's changed-line diff.
changed="$(git diff --numstat "$BASE"...HEAD | awk '{sum += $1 + $2} END {print sum + 0}')"
if [ "$changed" -gt 600 ]; then
  echo "PR exceeds the size limit"
  exit 1
fi
EOF

make_repo deferred-exit
cat >"$workspace/deferred-exit/scripts/preflight.sh" <<'EOF'
status=0
if [ "$CHANGED" -gt "$MAX_LINES" ]; then
  status=1
fi
exit "$status"
EOF

make_repo deferred-zero-status
cat >"$workspace/deferred-zero-status/scripts/preflight.sh" <<'EOF'
status=0
if [ "$CHANGED" -gt "$MAX_LINES" ]; then
  status=0 # Advisory reporting remains successful.
fi
exit "$status"
EOF

make_repo dynamic-exit
cat >"$workspace/dynamic-exit/scripts/preflight.sh" <<'EOF'
if [ "$changed_lines" -ge 600 ]; then
  exit "$failure_status"
fi
EOF

make_repo compact-exit
cat >"$workspace/compact-exit/scripts/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then echo "PR exceeds the size limit"; exit 1; fi
EOF

make_repo conditional-list-exit
cat >"$workspace/conditional-list-exit/scripts/preflight.sh" <<'EOF'
[ "$CHANGED" -le 600 ] || exit 1
EOF

make_repo conditional-list-multiline
cat >"$workspace/conditional-list-multiline/scripts/preflight.sh" <<'EOF'
test "$CHANGED" -le 600 ||
  exit 1
EOF

make_repo conditional-list-zero-exit
cat >"$workspace/conditional-list-zero-exit/scripts/preflight.sh" <<'EOF'
test "$CHANGED" -gt 600 && exit
EOF

make_repo errexit-standalone
cat >"$workspace/errexit-standalone/scripts/preflight.sh" <<'EOF'
set -euo pipefail
[ "$CHANGED" -le 600 ]
EOF

make_repo errexit-disabled
cat >"$workspace/errexit-disabled/scripts/preflight.sh" <<'EOF'
set -e
set +e
[ "$CHANGED" -le 600 ]
EOF

make_repo alternate-workflow-name
cat >"$workspace/alternate-workflow-name/.github/workflows/custom-pr-size.yaml" <<'EOF'
jobs:
  size:
    uses: SecPal/.github/.github/workflows/reusable-pr-size.yml@main
EOF

make_repo lowercase-owner-reference
cat >"$workspace/lowercase-owner-reference/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    uses: secpal/.github/.github/workflows/reusable-pr-size.yml@main
EOF

make_repo hard-pinned-revision
cat >"$workspace/hard-pinned-revision/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    uses: SecPal/.github/.github/workflows/reusable-pr-size.yml@57031ba8418e5febd39210a8bbcc7cb091b039a6
EOF

make_repo workflow-step-boundary
cat >"$workspace/workflow-step-boundary/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - if: env.CHANGED > 600
        run: echo "::warning::PR size advisory threshold exceeded"
      - run: exit 1
EOF

make_repo workflow-indentless-steps
cat >"$workspace/workflow-indentless-steps/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
    - run: |
        if [ "$CHANGED" -gt 600 ]; then
          exit 1
        fi
EOF

make_repo workflow-folded-condition
cat >"$workspace/workflow-folded-condition/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - if: >-
          env.CHANGED > 600
        run: exit 1
EOF

make_repo workflow-flow-style-steps
cat >"$workspace/workflow-flow-style-steps/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps: [{run: 'if [ "$CHANGED" -gt 600 ]; then exit 1; fi'}]
EOF

make_repo malformed-workflow-yaml
printf 'jobs: [\n' >"$workspace/malformed-workflow-yaml/.github/workflows/pr-size.yml"

make_repo workflow-if-hard-exit
cat >"$workspace/workflow-if-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - if: env.CHANGED > 600
        run: exit 1
EOF

make_repo workflow-job-if-hard-exit
cat >"$workspace/workflow-job-if-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    if: needs.diff.outputs.changed > 600
    steps:
      - run: exit 1
EOF

make_repo workflow-job-if-advisory
cat >"$workspace/workflow-job-if-advisory/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    if: needs.diff.outputs.changed > 600
    steps:
      - run: echo "::warning::PR size advisory threshold exceeded"
EOF

make_repo workflow-boolean-condition
cat >"$workspace/workflow-boolean-condition/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    if: true
    steps:
      - run: echo "PR size policy remains advisory"
EOF

make_repo workflow-template-advisory
mkdir -p "$workspace/workflow-template-advisory/workflow-templates"
cat >"$workspace/workflow-template-advisory/workflow-templates/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: echo "PR size advisory threshold is $CHANGED"
EOF

make_repo workflow-template-hard-exit
mkdir -p "$workspace/workflow-template-hard-exit/workflow-templates"
cat >"$workspace/workflow-template-hard-exit/workflow-templates/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - run: |
          if [ "$CHANGED" -gt 600 ]; then
            exit 1
          fi
EOF

make_repo workflow-python-hard-exit
cat >"$workspace/workflow-python-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - shell: python
        run: |
          import sys
          if changed_lines > 600:
              sys.exit(1)
EOF

make_repo workflow-default-python-hard-exit
cat >"$workspace/workflow-default-python-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
defaults:
  run:
    shell: python
jobs:
  size:
    steps:
      - run: |
          if changed_lines > 600:
              raise SystemExit(1)
EOF

make_repo job-default-python-advisory
cat >"$workspace/job-default-python-advisory/.github/workflows/pr-size.yml" <<'EOF'
defaults:
  run:
    shell: bash
jobs:
  size:
    defaults:
      run:
        shell: python
    steps:
      - run: |
          if changed_lines > 600:
              print("PR size advisory threshold exceeded")
EOF

make_repo composite-python-hard-exit
mkdir -p "$workspace/composite-python-hard-exit/.github/actions"
cat >"$workspace/composite-python-hard-exit/.github/actions/action.yml" <<'EOF'
runs:
  using: composite
  steps:
    - shell: python
      run: |
        import sys
        if changed_lines > 600:
            sys.exit(1)
EOF

make_repo composite-python-advisory
mkdir -p "$workspace/composite-python-advisory/.github/actions/pr-size"
cat >"$workspace/composite-python-advisory/.github/actions/pr-size/action.yml" <<'EOF'
runs:
  using: composite
  steps:
    - shell: python
      run: |
        if changed_lines > 600:
            print("PR size advisory threshold exceeded")
EOF

make_repo workflow-javascript-hard-exit
cat >"$workspace/workflow-javascript-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - shell: node {0}
        run: |
          if (changedLines > 600) {
            process.exit(1);
          }
EOF

make_repo javascript-multiline-exit
cat >"$workspace/javascript-multiline-exit/scripts/check-pr-size.mjs" <<'EOF'
if (
  changedLines > 600
) {
  process.exit(1);
}
EOF

make_repo conditional-action-hard-exit
mkdir -p "$workspace/conditional-action-hard-exit/.github/actions/pr-size"
cat >"$workspace/conditional-action-hard-exit/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - if: env.CHANGED > 600
        uses: ./.github/actions/pr-size
EOF
cat >"$workspace/conditional-action-hard-exit/.github/actions/pr-size/action.yml" <<'EOF'
runs:
  using: composite
  steps:
    - shell: bash
      run: exit 1
EOF

make_repo conditional-action-advisory
mkdir -p "$workspace/conditional-action-advisory/.github/actions/pr-size"
cat >"$workspace/conditional-action-advisory/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - if: env.CHANGED > 600
        uses: ./.github/actions/pr-size
EOF
cat >"$workspace/conditional-action-advisory/.github/actions/pr-size/action.yml" <<'EOF'
runs:
  using: composite
  steps:
    - shell: bash
      run: echo "PR size advisory threshold exceeded"
EOF

make_repo workflow-nonblocking-step
cat >"$workspace/workflow-nonblocking-step/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - continue-on-error: true
        run: |
          if [ "$CHANGED" -gt 600 ]; then
            exit 1
          fi
EOF

make_repo workflow-nonblocking-job
cat >"$workspace/workflow-nonblocking-job/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    continue-on-error: true
    steps:
      - run: |
          if [ "$CHANGED" -gt 600 ]; then
            exit 1
          fi
EOF

make_repo workflow-blocking-step
cat >"$workspace/workflow-blocking-step/.github/workflows/pr-size.yml" <<'EOF'
jobs:
  size:
    steps:
      - continue-on-error: false
        run: |
          if [ "$CHANGED" -gt 600 ]; then
            exit 1
          fi
EOF

make_repo python-exit
cat >"$workspace/python-exit/scripts/check_pr_size.py" <<'EOF'
import sys

if changed_lines > 600:
    sys.exit(1)
EOF

make_repo python-raise
cat >"$workspace/python-raise/scripts/check_pr_size.py" <<'EOF'
if changed_lines > 600:
    raise RuntimeError("PR is too large")
EOF

make_repo python-multiline-exit
cat >"$workspace/python-multiline-exit/scripts/check_pr_size.py" <<'EOF'
if (
    changed_lines
    > 600
):
    raise SystemExit(1)
EOF

make_repo python-assert
cat >"$workspace/python-assert/scripts/check_pr_size.py" <<'EOF'
assert changed_lines <= 600, "PR is too large"
EOF

make_repo python-caught-exception
cat >"$workspace/python-caught-exception/scripts/check_pr_size.py" <<'EOF'
try:
    if changed_lines > 600:
        raise ValueError("advisory threshold exceeded")
except ValueError:
    print("PR size advisory threshold exceeded")
EOF

make_repo python-caught-then-exit
cat >"$workspace/python-caught-then-exit/scripts/check_pr_size.py" <<'EOF'
try:
    if changed_lines > 600:
        raise ValueError("threshold exceeded")
except ValueError:
    raise SystemExit(1)
EOF

make_repo python-return-exit
cat >"$workspace/python-return-exit/scripts/check_pr_size.py" <<'EOF'
def main():
    if policy_enabled:
        if changed_lines > max_lines:
            return 1
    return 0


raise SystemExit(main())
EOF

make_repo python-library-return
cat >"$workspace/python-library-return/scripts/report_pr_size.py" <<'EOF'
def report(changed_lines, max_lines):
    if changed_lines > max_lines:
        return 1
    return 0


# raise SystemExit(report(changed_lines, max_lines))
EOF

make_repo python-zero-status
cat >"$workspace/python-zero-status/scripts/report_pr_size.py" <<'EOF'
def main():
    if changed_lines > max_lines:
        return False
    return None


raise SystemExit(main())
EOF

make_repo javascript-exit
cat >"$workspace/javascript-exit/scripts/check-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  process.exit(1);
}
EOF

make_repo javascript-exit-code
cat >"$workspace/javascript-exit-code/scripts/check-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  process.exitCode = 1;
}
EOF

make_repo javascript-compound-exit-code
cat >"$workspace/javascript-compound-exit-code/scripts/check-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  process.exitCode ||= 1;
}
EOF

make_repo javascript-throw
cat >"$workspace/javascript-throw/scripts/check-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  throw new Error("PR is too large");
}
EOF

make_repo javascript-zero-exit-code
cat >"$workspace/javascript-zero-exit-code/scripts/report-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  process.exitCode = 0;
}
EOF

make_repo diff-size-alias
cat >"$workspace/diff-size-alias/scripts/preflight.sh" <<'EOF'
DIFF_SIZE="$(git diff --numstat "$BASE"...HEAD | awk '{sum += $1 + $2} END {print sum + 0}')"
if [ "$DIFF_SIZE" -gt 600 ]; then
  exit 1
fi
EOF

make_repo derived-size-alias
cat >"$workspace/derived-size-alias/scripts/preflight.sh" <<'EOF'
DELTA="$(
  git diff --numstat "$BASE"...HEAD |
    awk '{sum += $1 + $2} END {print sum + 0}'
)"
if [ "$DELTA" -gt 600 ]; then
  exit 1
fi
EOF

make_repo unrelated-size
cat >"$workspace/unrelated-size/scripts/check-artifact.sh" <<'EOF'
if [ "$ARTIFACT_SIZE" -gt 600 ]; then
  exit 1
fi
EOF

make_repo unrelated-changed-counter
cat >"$workspace/unrelated-changed-counter/scripts/check-generated.sh" <<'EOF'
changed=1
if [ "$changed" -gt 0 ]; then
  echo "Generated sources need an update"
  exit 1
fi
EOF

make_repo commented-shell-gate
cat >"$workspace/commented-shell-gate/scripts/preflight.sh" <<'EOF'
# Historical policy, intentionally disabled:
# if [ "$CHANGED" -gt 600 ]; then
#   exit 1
# fi
echo "PR size remains advisory"
EOF

make_repo quoted-shell-gate
cat >"$workspace/quoted-shell-gate/scripts/preflight.sh" <<'EOF'
CHANGED="$(git diff --numstat "$BASE"...HEAD | awk '{sum += $1 + $2} END {print sum + 0}')"
echo 'if [ "$CHANGED" -gt 600 ]; then exit 1; fi'
EOF

make_repo commented-reusable-contract
cat >"$workspace/commented-reusable-contract/.github/workflows/reusable-pr-size.yml" <<'EOF'
# git diff --numstat
# INSERTIONS DELETIONS
# ::warning::
# Advisory changed-line threshold
jobs:
  size:
    steps:
      - run: echo "No PR-size reporting is implemented"
EOF

make_repo quoted-reusable-contract
cat >"$workspace/quoted-reusable-contract/.github/workflows/reusable-pr-size.yml" <<'EOF'
on:
  workflow_call:
    inputs:
      max-lines:
        description: Advisory changed-line threshold
permissions:
  contents: read
jobs:
  size:
    steps:
      - run: |
          echo 'git diff --numstat'
          echo 'INSERTIONS DELETIONS'
          echo '::warning::'
EOF

make_repo root-hook-advisory
cat >"$workspace/root-hook-advisory/.pre-commit-config.yaml" <<'EOF'
repos:
  - repo: local
    hooks:
      - id: pr-size
        name: Report PR size
        language: system
        entry: bash -c 'if [ "$changed_lines" -gt 600 ]; then echo "PR size advisory threshold exceeded"; fi'
EOF

make_repo root-hook-hard-exit
cat >"$workspace/root-hook-hard-exit/.pre-commit-config.yaml" <<'EOF'
repos:
  - repo: local
    hooks:
      - id: pr-size
        name: Enforce PR size
        language: system
        entry: bash -c 'if [ "$changed_lines" -gt 600 ]; then exit 1; fi'
EOF

make_repo unreadable-policy
# shellcheck disable=SC2016 # Fixture variables must remain literal.
printf '# invalid UTF-8 comment: \377\nif [ "$CHANGED" -gt 600 ]; then exit 23; fi\n' \
  >"$workspace/unreadable-policy/scripts/preflight.sh"
chmod +x "$workspace/unreadable-policy/scripts/preflight.sh"

make_repo malformed-javascript
cat >"$workspace/malformed-javascript/scripts/check-pr-size.mjs" <<'EOF'
if (changedLines > 600) {
  process.exit(1);
EOF

make_repo zero-exit
cat >"$workspace/zero-exit/scripts/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then
  exit 0
fi
EOF

make_repo advisory-typescript
mkdir -p "$workspace/advisory-typescript/src"
cat >"$workspace/advisory-typescript/src/report.ts" <<'EOF'
export function reportSize(changedLines: number, threshold: number): string {
  if (changedLines > threshold) {
    console.warn("Advisory PR-size threshold exceeded");
  }
  return "reported";
}
EOF

make_repo ignored-context
mkdir -p "$workspace/ignored-context/.context/review-fixture"
cat >"$workspace/ignored-context/.context/review-fixture/preflight.sh" <<'EOF'
if [ "$CHANGED" -gt 600 ]; then
  exit 1
fi
EOF

make_repo suffixless-binary
printf '\177ELF\000\377\376\375' >"$workspace/suffixless-binary/scripts/helper"
chmod +x "$workspace/suffixless-binary/scripts/helper"

make_repo tracked-context
mkdir -p "$workspace/tracked-context/.context"
printf 'agent scratch\n' >"$workspace/tracked-context/.context/note.txt"
(
  cd "$workspace/tracked-context"
  git init --quiet --initial-branch=main
  git add -f .context/note.txt
)

if ! bash "$validator" \
  "$workspace/advisory" \
  "$workspace/advisory-typescript" \
  "$workspace/conditional-list-zero-exit" \
  "$workspace/commented-shell-gate" \
  "$workspace/conditional-action-advisory" \
  "$workspace/deferred-zero-status" \
  "$workspace/errexit-disabled" \
  "$workspace/no-gate" \
  "$workspace/python-caught-exception" \
  "$workspace/zero-exit" \
  "$workspace/ignored-context" \
  "$workspace/javascript-zero-exit-code" \
  "$workspace/job-default-python-advisory" \
  "$workspace/python-library-return" \
  "$workspace/python-zero-status" \
  "$workspace/quoted-shell-gate" \
  "$workspace/root-hook-advisory" \
  "$workspace/suffixless-binary" \
  "$workspace/unrelated-size" \
  "$workspace/unrelated-changed-counter" \
  "$workspace/workflow-boolean-condition" \
  "$workspace/workflow-job-if-advisory" \
  "$workspace/workflow-step-boundary" \
  "$workspace/workflow-nonblocking-job" \
  "$workspace/workflow-nonblocking-step" \
  "$workspace/workflow-template-advisory" \
  "$workspace/composite-python-advisory" \
  "$repo_root" >"$workspace/pass.out"; then
  cat "$workspace/pass.out" >&2
  echo "Expected advisory fixtures to pass policy validation" >&2
  exit 1
fi
grep -Fq "advisory: PASS" "$workspace/pass.out"
grep -Fq "advisory-typescript: PASS" "$workspace/pass.out"
grep -Fq "conditional-list-zero-exit: PASS" "$workspace/pass.out"
grep -Fq "commented-shell-gate: PASS" "$workspace/pass.out"
grep -Fq "conditional-action-advisory: PASS" "$workspace/pass.out"
grep -Fq "deferred-zero-status: PASS" "$workspace/pass.out"
grep -Fq "errexit-disabled: PASS" "$workspace/pass.out"
grep -Fq "no-gate: PASS" "$workspace/pass.out"
grep -Fq "python-caught-exception: PASS" "$workspace/pass.out"
grep -Fq "zero-exit: PASS" "$workspace/pass.out"
grep -Fq "ignored-context: PASS" "$workspace/pass.out"
grep -Fq "javascript-zero-exit-code: PASS" "$workspace/pass.out"
grep -Fq "job-default-python-advisory: PASS" "$workspace/pass.out"
grep -Fq "python-library-return: PASS" "$workspace/pass.out"
grep -Fq "python-zero-status: PASS" "$workspace/pass.out"
grep -Fq "quoted-shell-gate: PASS" "$workspace/pass.out"
grep -Fq "root-hook-advisory: PASS" "$workspace/pass.out"
grep -Fq "suffixless-binary: PASS" "$workspace/pass.out"
grep -Fq "unrelated-size: PASS" "$workspace/pass.out"
grep -Fq "unrelated-changed-counter: PASS" "$workspace/pass.out"
grep -Fq "workflow-boolean-condition: PASS" "$workspace/pass.out"
grep -Fq "workflow-job-if-advisory: PASS" "$workspace/pass.out"
grep -Fq "workflow-step-boundary: PASS" "$workspace/pass.out"
grep -Fq "workflow-nonblocking-job: PASS" "$workspace/pass.out"
grep -Fq "workflow-nonblocking-step: PASS" "$workspace/pass.out"
grep -Fq "workflow-template-advisory: PASS" "$workspace/pass.out"
grep -Fq "composite-python-advisory: PASS" "$workspace/pass.out"

for invalid in \
  alternate-workflow-name \
  composite-python-hard-exit \
  commented-reusable-contract \
  compact-exit \
  conditional-list-exit \
  conditional-list-multiline \
  conditional-action-hard-exit \
  deferred-exit \
  derived-size-alias \
  diff-size-alias \
  errexit-standalone \
  hard-pinned-revision \
  javascript-compound-exit-code \
  javascript-multiline-exit \
  javascript-exit \
  javascript-exit-code \
  javascript-throw \
  hard-exit \
  lowercase-owner-reference \
  malformed-javascript \
  malformed-workflow-yaml \
  override-file \
  label-override \
  python-exit \
  python-assert \
  python-caught-then-exit \
  python-multiline-exit \
  python-raise \
  python-return-exit \
  quoted-reusable-contract \
  unreadable-policy \
  workflow-if-hard-exit \
  workflow-folded-condition \
  workflow-flow-style-steps \
  workflow-indentless-steps \
  workflow-job-if-hard-exit \
  workflow-blocking-step \
  workflow-failure \
  workflow-javascript-hard-exit \
  workflow-default-python-hard-exit \
  workflow-python-hard-exit \
  workflow-template-hard-exit \
  exit-three \
  lowercase-variable \
  root-hook-hard-exit \
  dynamic-exit \
  tracked-context; do
  validator_arguments=("$workspace/$invalid")
  if [ "$invalid" = "hard-pinned-revision" ]; then
    validator_arguments+=("$repo_root")
  fi
  if bash "$validator" "${validator_arguments[@]}" >"$workspace/$invalid.out" 2>&1; then
    echo "Expected $invalid fixture to fail policy validation" >&2
    exit 1
  fi
  grep -Fq "$invalid: FAIL" "$workspace/$invalid.out"
done

managed_workspace="$workspace/managed"
managed_repositories=(
  .github
  api
  frontend
  contracts
  android
  GuardGuide
  guardguide.de
  secpal.app
)
for repository in "${managed_repositories[@]}"; do
  mkdir -p "$managed_workspace/$repository"
done
bash "$validator" "$managed_workspace" >"$workspace/managed.out"
for repository in "${managed_repositories[@]}"; do
  grep -Fq "$repository: PASS" "$workspace/managed.out"
done

# A repository preflight must remain runnable from an isolated checkout. The
# explicit multi-repository command above covers workspace-wide auditing.
bash "$validator" "$repo_root"

grep -Fq "bash tests/validate-pr-size-policy.sh" "$preflight"

echo "tests/validate-pr-size-policy.sh: organization-wide policy verified."
