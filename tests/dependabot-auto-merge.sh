#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
#
# Regression tests for the .github repository's Dependabot caller and reusable
# workflows. Verifies the caller explicitly grants the write permissions
# required by the reusable workflow and that both workflows gate on the PR
# author rather than the event actor so maintainer-triggered `reopened` and
# `ready_for_review` events on Dependabot-authored PRs still enroll in
# auto-merge.
#
# shellcheck disable=SC2016 # This test intentionally matches literal GitHub expressions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=tests/android-consumed-workflow-action-pins.sh
source "$SCRIPT_DIR/android-consumed-workflow-action-pins.sh"
CALLER_WORKFLOW="$REPO_ROOT/.github/workflows/dependabot-auto-merge.yml"
REUSABLE_WORKFLOW="$REPO_ROOT/.github/workflows/reusable-dependabot-auto-merge.yml"
DEPENDABOT_CONFIG="$REPO_ROOT/.github/dependabot.yml"
WORKFLOW_INSTRUCTIONS="$REPO_ROOT/.github/instructions/github-workflows.instructions.md"
WORKFLOW_EXAMPLE="$REPO_ROOT/EXAMPLE_workflow_for_other_repos.yml"
WORKFLOW_CATALOG_README="$REPO_ROOT/.github/workflows/README.md"
ROLLOUT_GUIDE="$REPO_ROOT/docs/workflows/ROLLOUT_GUIDE.md"
QUALITY_WORKFLOW="$REPO_ROOT/.github/workflows/quality.yml"

resolve_base_revision() {
  local repository="$1"
  local candidate revision

  if [[ -n "${SECPAL_BASE_REVISION:-}" ]]; then
    git -C "$repository" rev-parse --verify "$SECPAL_BASE_REVISION^{commit}"
    return
  fi

  for candidate in refs/heads/main refs/remotes/origin/main; do
    if revision="$(git -C "$repository" rev-parse --verify "$candidate^{commit}" 2>/dev/null)"; then
      printf '%s\n' "$revision"
      return 0
    fi
  done
  return 1
}

base_fixture="$(mktemp -d "${TMPDIR:-/tmp}/dependabot-auto-merge.XXXXXX")"
trap 'rm -rf "$base_fixture"' EXIT
git -C "$base_fixture" init --quiet --initial-branch=main
git -C "$base_fixture" \
  -c user.name='SecPal Tests' \
  -c user.email='tests@secpal.dev' \
  -c commit.gpgsign=false \
  commit --quiet --allow-empty --message='Create test baseline'
fixture_main_revision="$(git -C "$base_fixture" rev-parse refs/heads/main)"
if [[ "$(SECPAL_BASE_REVISION='' resolve_base_revision "$base_fixture" 2>/dev/null || true)" != "$fixture_main_revision" ]]; then
  echo "Dependabot caller workflow validation must support a local main branch without an origin remote." >&2
  exit 1
fi
if [[ "$(SECPAL_BASE_REVISION="$fixture_main_revision" resolve_base_revision "$base_fixture")" != "$fixture_main_revision" ]]; then
  echo "Dependabot caller workflow validation must honor an explicit base revision." >&2
  exit 1
fi

for workflow in "$CALLER_WORKFLOW" "$REUSABLE_WORKFLOW"; do
  if [ ! -f "$workflow" ]; then
    echo "Expected workflow was not found: $workflow" >&2
    exit 1
  fi

  marker_count="$(grep -c '^---$' "$workflow")"
  if [ "$marker_count" -ne 1 ]; then
    echo "Dependabot workflows must contain exactly one YAML document marker: $workflow" >&2
    exit 1
  fi
done

grep -q '^---$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must include a YAML document marker." >&2
  exit 1
}

grep -q '^name: Dependabot Auto-Merge$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must declare its workflow name." >&2
  exit 1
}

if ! awk '
  /^---$/ { marker = NR; next }
  /^name: Dependabot Auto-Merge$/ { name = NR }
  END { exit !(marker > 0 && name == marker + 1) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow YAML document marker must appear immediately before name:." >&2
  exit 1
fi

if [ ! -f "$WORKFLOW_INSTRUCTIONS" ]; then
  echo "Expected workflow instructions were not found: $WORKFLOW_INSTRUCTIONS" >&2
  exit 1
fi

workflow_instruction_scope="$(
  sed -n 's/^applyTo: "\(.*\)"$/\1/p' "$WORKFLOW_INSTRUCTIONS"
)"
IFS=',' read -r -a workflow_instruction_patterns <<< "$workflow_instruction_scope"
for direct_fixture in \
  .github/actions/setup-node-with-deps/action.yml \
  tests/android-consumed-workflow-action-pins.sh \
  tests/codeql-applicability.sh \
  tests/copilot-review-memory-errors.sh \
  tests/copilot-review-memory.sh \
  tests/dependabot-auto-merge.sh \
  tests/deploy-main-workflow.sh \
  tests/license-compatibility.sh \
  tests/prettier-version-alignment.sh \
  tests/project-automation-core.sh \
  tests/pull-request-commit-signatures.sh \
  tests/pull-request-english.sh \
  tests/pull-request-evidence.sh \
  tests/reusable-markdown-lint-scope.sh \
  tests/reusable-workflow-policy.sh \
  tests/reusable-workflow-timeouts.sh; do
  fixture_is_scoped=0
  for instruction_pattern in "${workflow_instruction_patterns[@]}"; do
    if compgen -G "$REPO_ROOT/$instruction_pattern" | grep -Fxq "$REPO_ROOT/$direct_fixture"; then
      fixture_is_scoped=1
      break
    fi
  done
  if [[ "$fixture_is_scoped" -ne 1 ]]; then
    echo "Workflow instructions must apply to direct validation fixture: $direct_fixture" >&2
    exit 1
  fi
done

if [ ! -f "$WORKFLOW_EXAMPLE" ]; then
  echo "Expected workflow example was not found: $WORKFLOW_EXAMPLE" >&2
  exit 1
fi

if [ ! -f "$WORKFLOW_CATALOG_README" ]; then
  echo "Expected workflow catalog README was not found: $WORKFLOW_CATALOG_README" >&2
  exit 1
fi

if [ ! -f "$ROLLOUT_GUIDE" ]; then
  echo "Expected rollout guide was not found: $ROLLOUT_GUIDE" >&2
  exit 1
fi

if [ ! -f "$DEPENDABOT_CONFIG" ]; then
  echo "Expected Dependabot configuration was not found: $DEPENDABOT_CONFIG" >&2
  exit 1
fi

grep -q '^  - package-ecosystem: "github-actions"$' "$DEPENDABOT_CONFIG" || {
  echo "Dependabot must continue to update immutable GitHub Actions references." >&2
  exit 1
}

if ! awk '
  /^---$/ { document_start_markers++ }
  /^----+$/ { malformed_document_markers++ }
  END { exit !(document_start_markers == 1 && malformed_document_markers == 0) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must contain exactly one valid YAML document start marker." >&2
  exit 1
fi

grep -q '^permissions:$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must declare explicit permissions." >&2
  exit 1
}

grep -q '^  contents: write$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must grant contents: write." >&2
  exit 1
}

grep -q '^  pull-requests: write$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must grant pull-requests: write." >&2
  exit 1
}

# Gate on the PR author (github.event.pull_request.user.login) rather than the
# event actor (github.actor). The actor is the user who triggered the latest
# event, which for `reopened` / `ready_for_review` is often a maintainer rather
# than Dependabot itself. Gating on the author preserves the Dependabot-only
# scope while still enrolling maintainer-triggered events on Dependabot PRs.
grep -q "^    if: github.event.pull_request.user.login == 'dependabot\\[bot\\]'$" "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must gate on github.event.pull_request.user.login so maintainer-triggered reopened / ready_for_review events on Dependabot PRs are not skipped." >&2
  exit 1
}

# Defensive guard against regression: the brittle actor-based gate must not
# come back, because it silently skips auto-merge enrollment whenever a
# maintainer reopens or marks a Dependabot PR as ready for review. The
# pattern is anchored to real YAML `if:` lines so explanatory comments or
# documentation that mention the old `github.actor` pattern do not trip the
# check.
if grep -qE "^[[:space:]]+if:.*github\.actor == 'dependabot\[bot\]'" "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not gate on github.actor; use github.event.pull_request.user.login instead so maintainer-triggered events on Dependabot PRs are not skipped." >&2
  exit 1
fi

grep -qE '^    uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@[0-9a-f]{40}[[:space:]]+#[[:space:]]+main$' "$CALLER_WORKFLOW" || {
  echo "Dependabot caller workflow must keep auto-merge decisions on a reviewed immutable reusable workflow revision documented as main." >&2
  exit 1
}

caller_revision="$(
  sed -nE \
    's|^[[:space:]]+uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@([0-9a-f]{40})[[:space:]]+#.*$|\1|p' \
    "$CALLER_WORKFLOW"
)"
main_revision="$(resolve_base_revision "$REPO_ROOT")" || {
  echo "Dependabot caller workflow validation requires an explicit or locally available main revision." >&2
  exit 1
}
git -C "$REPO_ROOT" merge-base --is-ancestor "$caller_revision" "$main_revision" || {
  echo "Dependabot caller workflow revision must already be reachable from main." >&2
  exit 1
}
if awk '
  /^  auto-merge:$/ { in_job = 1; next }
  in_job && /^  [[:alnum:]_-]+:$/ { in_job = 0 }
  in_job && /^[[:space:]]+uses: SecPal\/\.github\/\.github\/workflows\/reusable-dependabot-auto-merge\.yml@[0-9a-f]{40}[[:space:]]+#[[:space:]]+main$/ {
    reusable_job = 1
  }
  in_job && /^[[:space:]]+timeout-minutes:/ { has_timeout = 1 }
  END { exit !(reusable_job && has_timeout) }
' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not set timeout-minutes on a reusable workflow caller job." >&2
  exit 1
fi

normalized_workflow_instructions="$(
  tr '\n' ' ' < "$WORKFLOW_INSTRUCTIONS" | tr -s '[:space:]' ' '
)"
if [[ "$normalized_workflow_instructions" != *'A reusable-workflow caller job using `jobs.<job_id>.uses` cannot set a timeout; the called workflow must bound each of its jobs.'* ]]; then
  echo "Workflow instructions must document the reusable-workflow caller timeout-minutes exception." >&2
  exit 1
fi

awk '
  /^  workflow-pins:$/ { in_job = 1; next }
  in_job && /^  [A-Za-z0-9_-]+:$/ { in_job = 0 }
  in_job && /^      - name: Setup Node\.js$/ { sets_up_node = 1 }
  in_job && /^      - name: Install Node dependencies$/ { installs_dependencies = 1 }
  in_job && /^        run: npm ci$/ { uses_lockfile = 1 }
  in_job && /^      - name: Verify external workflow references$/ { in_step = 1; next }
  in_step && /^      - name:/ { in_step = 0 }
  in_step && /^          VERIFY_ACTION_PIN_PROVENANCE: "true"$/ { verifies_provenance = 1 }
  in_step && /^          bash tests\/android-consumed-workflow-action-pins\.sh$/ { validates_working_tree = 1 }
  in_step && /^          bash tests\/dependabot-auto-merge\.sh$/ { validates_pinned_snapshot = 1 }
  END {
    exit !(sets_up_node && installs_dependencies && uses_lockfile &&
      verifies_provenance && validates_working_tree && validates_pinned_snapshot)
  }
' "$QUALITY_WORKFLOW" || {
  echo "Workflow pin validation must install locked Node dependencies and verify both the working tree and pinned Dependabot snapshot with live provenance enabled." >&2
  exit 1
}
# The reusable workflow's check-eligibility and skip-auto-merge jobs must also
# gate on the PR author so the same maintainer-triggered events are not
# skipped when other repositories invoke this reusable workflow directly.
grep -q "^    if: github.event.pull_request.user.login == 'dependabot\\[bot\\]'$" "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must gate check-eligibility on github.event.pull_request.user.login so maintainer-triggered reopened / ready_for_review events on Dependabot PRs are not skipped." >&2
  exit 1
}

awk '
  /^  skip-auto-merge:$/ { in_job = 1; next }
  in_job && /^  [[:alnum:]_-]+:$/ { in_job = 0 }
  in_job && /needs\.check-eligibility\.outputs\.should-auto-merge != '\''true'\''/ { has_output_guard = 1 }
  in_job && /github\.event\.pull_request\.user\.login == '\''dependabot\[bot\]'\''/ { has_author_guard = 1 }
  END { exit !(has_output_guard && has_author_guard) }
' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must gate skip-auto-merge on github.event.pull_request.user.login so maintainer-triggered events on Dependabot PRs still receive the manual-review comment." >&2
  exit 1
}

grep -q '^        uses: dependabot/fetch-metadata@25dd0e34f4fe68f24cc83900b1fe3fe149efef98 # v3.1.0$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must pin dependabot/fetch-metadata to the v3.1.0 commit with the null update-type fix." >&2
  exit 1
}

validate_immutable_action_references() {
  local parser=()
  local source_name yaml_json

  if [[ $# -gt 1 ]]; then
    echo "Immutable action reference validation accepts at most one workflow path." >&2
    return 1
  fi

  if [[ -x "$REPO_ROOT/node_modules/.bin/js-yaml" ]]; then
    parser=("$REPO_ROOT/node_modules/.bin/js-yaml")
  else
    echo "Immutable action reference validation requires dependencies installed with npm ci." >&2
    return 1
  fi

  source_name="${1:-standard input}"
  yaml_json="$("${parser[@]}" "$@")" || return 1

  printf '%s\n' "$yaml_json" |
  node -e '
    const fs = require("node:fs");
    const sourceName = process.argv[1];
    const workflow = JSON.parse(fs.readFileSync(0, "utf8"));
    let invalidReference = false;

    function validateReference(reference, location) {
      const repositoryPin = /^[^@\s]+@[0-9a-f]{40}$/i;
      const dockerPin = /^docker:\/\/[^@\s]+@sha256:[0-9a-f]{64}$/;
      let immutable = false;

      if (typeof reference === "string" && reference.startsWith("docker://")) {
        immutable = dockerPin.test(reference);
      } else if (typeof reference === "string" && !reference.startsWith("./")) {
        immutable = repositoryPin.test(reference);
      }

      if (!immutable) {
        process.stderr.write(`Movable nested action reference at ${location}: ${String(reference)}\n`);
        invalidReference = true;
      }
    }

    function validateWorkflow(workflow, sourceName) {
      if (workflow === null || typeof workflow !== "object" || Array.isArray(workflow)) {
        throw new Error(`${sourceName}: workflow document must be a mapping`);
      }

      const jobs = workflow.jobs;
      if (jobs === null || typeof jobs !== "object" || Array.isArray(jobs)) {
        return;
      }

      for (const [jobId, job] of Object.entries(jobs)) {
        if (job === null || typeof job !== "object" || Array.isArray(job)) {
          continue;
        }
        if (Object.prototype.hasOwnProperty.call(job, "uses")) {
          validateReference(job.uses, `${sourceName}: jobs.${jobId}.uses`);
        }
        if (!Array.isArray(job.steps)) {
          continue;
        }
        job.steps.forEach((step, index) => {
          if (step !== null && typeof step === "object" &&
              !Array.isArray(step) && Object.prototype.hasOwnProperty.call(step, "uses")) {
            validateReference(step.uses, `${sourceName}: jobs.${jobId}.steps[${index}].uses`);
          }
        });
      }
    }

    validateWorkflow(workflow, sourceName);
    process.exit(invalidReference ? 1 : 0);
  ' "$source_name"
}

validate_documented_action_release_pins() {
  local source_name="$1"
  local fixture_path="$base_fixture/action-pin-definition.yml"

  cat >"$fixture_path"
  validate_action_definition_pins "$fixture_path" "$source_name"
}

immutable_action_fixture='jobs:
  reusable-workflow:
    uses: actions/example/.github/workflows/example.yml@0123456789abcdef0123456789abcdef01234567
  action-steps:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/example@0123456789abcdef0123456789abcdef01234567
      - uses : actions/example@0123456789ABCDEF0123456789ABCDEF01234567
      - { name: Example, uses: "actions/example@0123456789abcdef0123456789abcdef01234567" }
      - uses: docker://alpine@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'

if ! printf '%s\n' "$immutable_action_fixture" | validate_immutable_action_references; then
  echo "Immutable action reference validation must accept Git commit pins in either hex case and canonical Docker digests in every valid step form." >&2
  exit 1
fi

for movable_action_fixture in \
  'jobs: { fixture: { uses: actions/example/.github/workflows/example.yml@v1 } }' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@main' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses : actions/example@v1' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - { name: Example, uses: actions/example@v1 }' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: ./.github/actions/local-check' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: ./.github/actions/local-check@0123456789abcdef0123456789abcdef01234567' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: docker://alpine@0123456789abcdef0123456789abcdef01234567' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: docker://alpine@sha256:0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF' \
  $'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: docker://alpine:latest'; do
  if printf '%s\n' "$movable_action_fixture" | validate_immutable_action_references 2>/dev/null; then
    echo "Immutable action reference validation accepted a movable reference: $movable_action_fixture" >&2
    exit 1
  fi
done

documented_release_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1.2.3'
if ! printf '%s\n' "$documented_release_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "documented release fixture"; then
  echo "Documented action release validation must accept exact releases." >&2
  exit 1
fi

documented_workflow_source_fixture=$'jobs:\n  fixture:\n    uses: actions/example/.github/workflows/example.yml@0123456789abcdef0123456789abcdef01234567 # main'
if ! printf '%s\n' "$documented_workflow_source_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "documented workflow source fixture"; then
  echo "Documented reusable workflow validation must accept source refs." >&2
  exit 1
fi

fake_parser_bin="$base_fixture/fake-parser-bin"
unlocked_fixture_root="$base_fixture/unlocked-repository"
mkdir -p "$fake_parser_bin" "$unlocked_fixture_root"
cat >"$fake_parser_bin/npx" <<'EOF'
#!/usr/bin/env bash
printf '{}\n'
EOF
chmod +x "$fake_parser_bin/npx"
rejects_unlocked_action_parser() {
  local repo_root="$unlocked_fixture_root"
  local PATH="$fake_parser_bin:$PATH"

  ! list_yaml_action_references "$base_fixture/action-pin-definition.yml" >/dev/null 2>&1
}
if ! rejects_unlocked_action_parser; then
  echo "Action reference validation downloaded a parser outside the repository lockfile." >&2
  exit 1
fi
rejects_unlocked_immutable_parser() {
  local REPO_ROOT="$unlocked_fixture_root"
  local PATH="$fake_parser_bin:$PATH"

  ! validate_immutable_action_references "$base_fixture/action-pin-definition.yml" >/dev/null 2>&1
}
if ! rejects_unlocked_immutable_parser; then
  echo "Immutable reference validation downloaded a parser outside the repository lockfile." >&2
  exit 1
fi

documented_docker_digest_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: docker://alpine@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
if ! printf '%s\n' "$documented_docker_digest_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "documented Docker digest fixture"; then
  echo "Documented action validation must accept canonical Docker digests." >&2
  exit 1
fi

unrelated_uses_fixture=$'inputs:\n  uses:\n    description: Ordinary composite action input\nenv:\n  uses: ordinary-value\nruns:\n  using: composite\n  steps:\n    - uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1.2.3'
if ! printf '%s\n' "$unrelated_uses_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "unrelated uses fixture"; then
  echo "Action reference validation must ignore uses keys outside action-bearing schema locations." >&2
  exit 1
fi

major_only_release_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1'
if printf '%s\n' "$major_only_release_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "major-only release fixture" 2>/dev/null; then
  echo "Documented action release validation accepted a mutable major-only label." >&2
  exit 1
fi

spaced_uses_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses : actions/example@0123456789abcdef0123456789abcdef01234567'
if printf '%s\n' "$spaced_uses_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "spaced uses fixture" 2>/dev/null; then
  echo "Documented action release validation ignored a spaced uses key without provenance." >&2
  exit 1
fi

inline_uses_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - { name: Example, uses: actions/example@0123456789abcdef0123456789abcdef01234567 }'
if printf '%s\n' "$inline_uses_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "inline uses fixture" 2>/dev/null; then
  echo "Documented action release validation ignored an inline uses key without provenance." >&2
  exit 1
fi

decoy_documentation_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    env:\n      uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1.2.3\n    steps:\n      - uses : actions/example@0123456789abcdef0123456789abcdef01234567'
if printf '%s\n' "$decoy_documentation_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "decoy documentation fixture" 2>/dev/null; then
  echo "Documented action release validation matched provenance from a different YAML location." >&2
  exit 1
fi

duplicate_jobs_fixture=$'jobs:\n  verified:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1.2.3\njobs:\n  movable:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@main'
if printf '%s\n' "$duplicate_jobs_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "duplicate jobs fixture" 2>/dev/null; then
  echo "Action reference validation accepted duplicate mappings that hide a movable reference." >&2
  exit 1
fi

multiple_documents_fixture=$'jobs:\n  verified:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@0123456789abcdef0123456789abcdef01234567 # v1.2.3\n---\njobs:\n  movable:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@main'
if printf '%s\n' "$multiple_documents_fixture" |
  VERIFY_ACTION_PIN_PROVENANCE=false \
    validate_documented_action_release_pins "multiple documents fixture" 2>/dev/null; then
  echo "Action reference validation accepted an unchecked additional YAML document." >&2
  exit 1
fi

mismatched_release_fixture=$'jobs:\n  fixture:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/example@1111111111111111111111111111111111111111 # v1.2.3'
if (
  # shellcheck disable=SC2329 # The validation function invokes this provenance hook indirectly.
  verify_action_release_pin() { return 1; }
  VERIFY_ACTION_PIN_PROVENANCE=true \
    validate_documented_action_release_pins \
      "mismatched release fixture" <<<"$mismatched_release_fixture" 2>/dev/null
); then
  echo "Pinned action provenance validation accepted a SHA that was not verified against its documented release." >&2
  exit 1
fi

# Cross-repository callers pin this reusable workflow to a commit, but that
# pin is only meaningful when every action it invokes is also immutable.
# Require a full commit SHA for repository actions and a canonical SHA-256
# digest for Docker actions so a movable or caller-local reference cannot
# silently change the code executed by consumers.
if ! validate_immutable_action_references "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must pin every nested repository action to a full commit SHA and every Docker action to a canonical SHA-256 digest; caller-local references are not allowed." >&2
  exit 1
fi

pinned_reusable_workflow="$(
  git -C "$REPO_ROOT" show \
    "$caller_revision:.github/workflows/reusable-dependabot-auto-merge.yml"
)" || {
  echo "Pinned Dependabot reusable workflow is unavailable from the reviewed revision." >&2
  exit 1
}
if ! printf '%s\n' "$pinned_reusable_workflow" |
  validate_immutable_action_references; then
  echo "Pinned Dependabot reusable workflow must keep every nested action immutable." >&2
  exit 1
fi
if ! printf '%s\n' "$pinned_reusable_workflow" |
  validate_documented_action_release_pins "pinned Dependabot reusable workflow"; then
  echo "Pinned Dependabot reusable workflow must retain exact release provenance for every nested action." >&2
  exit 1
fi

grep -q '^        continue-on-error: true$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must soft-fail fetch-metadata into the manual-review path." >&2
  exit 1
}

if grep -q '^          skip-verification: true$' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not bypass fetch-metadata commit verification." >&2
  exit 1
fi

grep -q '^#       uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@<trusted-commit-sha>$' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow usage example must tell external callers to pin the workflow to a reviewed immutable commit SHA." >&2
  exit 1
}

if grep -q '^#       uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow usage example must not steer callers back to the stale @v1 tag." >&2
  exit 1
fi

if grep -qE '^[[:space:]]+uses: SecPal/\.github/\.github/workflows/reusable-dependabot-auto-merge\.yml@v1$' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not self-reference the reusable workflow through the stale @v1 tag." >&2
  exit 1
fi

if grep -q '^    uses: \./\.github/workflows/reusable-dependabot-auto-merge\.yml$' "$CALLER_WORKFLOW"; then
  echo "Dependabot caller workflow must not execute the reusable workflow from the PR merge commit." >&2
  exit 1
fi

if grep -qE 'uses: SecPal/\.github/\.github/workflows/[^[:space:]]+@main$' "$WORKFLOW_EXAMPLE"; then
  echo "Workflow example must not steer cross-repository callers to moving @main refs." >&2
  exit 1
fi

grep -q '^    uses: SecPal/\.github/\.github/workflows/project-automation-v2\.yml@<trusted-commit-sha>$' "$WORKFLOW_EXAMPLE" || {
  echo "Workflow example must pin project automation to a trusted commit SHA." >&2
  exit 1
}

grep -q '^    uses: SecPal/\.github/\.github/workflows/draft-pr-reminder\.yml@<trusted-commit-sha>$' "$WORKFLOW_EXAMPLE" || {
  echo "Workflow example must pin draft PR reminder to a trusted commit SHA." >&2
  exit 1
}

if grep -qE 'uses: SecPal/\.github/\.github/workflows/[^[:space:]]+@main$' "$WORKFLOW_CATALOG_README"; then
  echo "Workflow catalog README must not steer cross-repository callers to moving @main refs." >&2
  exit 1
fi

grep -q '@<trusted-commit-sha>' "$WORKFLOW_CATALOG_README" || {
  echo "Workflow catalog README must document trusted commit SHA pinning for reusable workflows." >&2
  exit 1
}

ROLLOUT_GUIDE_MAIN_REF_PATTERN="^[[:space:]]*uses:[[:space:]]*['\"]?SecPal/\\.github/\\.github/workflows/[^[:space:]'\\\"]+@main['\"]?([[:space:]]*(#.*)?)?$"

printf 'Do not copy moving refs such as `@main` into consumer repositories.\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" && {
    echo "Rollout guide regression guard must allow prose warnings that mention @main." >&2
    exit 1
  }

printf 'Example prose: uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" && {
    echo "Rollout guide regression guard must ignore prose that embeds a uses: pin mid-line." >&2
    exit 1
  }

printf 'Example prose: uses: "SecPal/.github/.github/workflows/project-automation-v2.yml@main"\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" && {
    echo "Rollout guide regression guard must ignore prose that embeds a quoted uses: pin mid-line." >&2
    exit 1
  }

printf '    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" || {
    echo "Rollout guide regression guard must still reject uses: pins that track @main." >&2
    exit 1
  }

printf '    uses: SecPal/.github/.github/workflows/project-automation-v2.yml@main # rotate after review\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" || {
    echo "Rollout guide regression guard must still reject uses: pins that track @main when they carry inline comments." >&2
    exit 1
  }

printf '    uses: "SecPal/.github/.github/workflows/project-automation-v2.yml@main"\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" || {
    echo "Rollout guide regression guard must still reject quoted uses: pins that track @main." >&2
    exit 1
  }

printf '    uses: "SecPal/.github/.github/workflows/project-automation-v2.yml@main" # rotate after review\n' |
  grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" || {
    echo "Rollout guide regression guard must still reject quoted uses: pins that track @main when they carry inline comments." >&2
    exit 1
  }

if grep -qE "$ROLLOUT_GUIDE_MAIN_REF_PATTERN" "$ROLLOUT_GUIDE"; then
  echo "Rollout guide must not tell cross-repository consumers to track moving @main refs." >&2
  exit 1
fi

if grep -q '@v1\.0\.0' "$ROLLOUT_GUIDE"; then
  echo "Rollout guide must not steer cross-repository consumers to stale release tags." >&2
  exit 1
fi

grep -q '@<trusted-commit-sha>' "$ROLLOUT_GUIDE" || {
  echo "Rollout guide must document trusted commit SHA pinning for reusable workflows." >&2
  exit 1
}

grep -q '^# SPDX-FileCopyrightText: 2025-2026 SecPal$' "$REPO_ROOT/.github/workflows/quality.yml" || {
  echo "Quality workflow SPDX year must stay current when the file is edited." >&2
  exit 1
}

grep -Fq '          METADATA_STEP_OUTCOME: ${{ steps.metadata.outcome }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the fetch-metadata step outcome." >&2
  exit 1
}

grep -Fq '          DEPENDENCY_GROUP: ${{ steps.metadata.outputs.dependency-group }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the dependency-group metadata output." >&2
  exit 1
}

grep -Fq '          MAINTAINER_CHANGES: ${{ steps.metadata.outputs.maintainer-changes }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must surface the maintainer-changes metadata output." >&2
  exit 1
}

grep -Fq '          PR_TITLE: ${{ github.event.pull_request.title }}' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must expose the PR title for the metadata-empty fallback path." >&2
  exit 1
}

grep -Fq 'Fallback to PR title parsing only when fetch-metadata returns empty outputs' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must document the metadata-empty title fallback boundary." >&2
  exit 1
}

# Keep every metadata-empty GitHub Actions update on manual review, even when
# the PR title still looks semver-shaped. Title parsing is only allowed for
# non-GitHub-Actions ecosystems with empty fetch-metadata outputs.
grep -Fq 'elif [[ "${PACKAGE_ECOSYSTEM}" != "github-actions" ]] && fallback_from_pr_title; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must restrict the metadata-empty PR title fallback to non-GitHub-Actions ecosystems." >&2
  exit 1
}

grep -Fq 'if [[ "${MAINTAINER_CHANGES}" == "true" ]]; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must fail closed when Dependabot metadata reports maintainer changes." >&2
  exit 1
}

grep -Fq 'if [[ "${METADATA_STEP_OUTCOME}" != "success" ]]; then' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must fail closed when fetch-metadata itself cannot verify the PR." >&2
  exit 1
}

grep -Fq 'echo "update-type=maintainer-changes" >> "${GITHUB_OUTPUT}"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must classify maintainer-changed Dependabot PRs for manual review." >&2
  exit 1
}

grep -Fq '[[ -n "${DEPENDENCY_GROUP}" || "${DEPENDENCY_NAMES}" == *,* ]]' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must detect grouped Dependabot PRs conservatively." >&2
  exit 1
}

grep -Fq 'echo "update-type=grouped-update" >> "${GITHUB_OUTPUT}"' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must classify grouped Dependabot PRs for manual review." >&2
  exit 1
}

if grep -Fq 'Eligible for auto-merge (Phase 3): MAJOR' "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not auto-merge major updates in any phase." >&2
  exit 1
fi

grep -q 'MAJOR semver update requires manual review' "$REUSABLE_WORKFLOW" || {
  echo "Reusable Dependabot workflow must route major updates to manual review." >&2
  exit 1
}

# Same anchoring as the caller guard: only flag actual YAML `if:` lines so
# explanatory comments or documentation mentioning the old `github.actor`
# pattern do not trip the regression check.
if grep -qE "^[[:space:]]+if:.*github\.actor == 'dependabot\[bot\]'" "$REUSABLE_WORKFLOW"; then
  echo "Reusable Dependabot workflow must not gate on github.actor; use github.event.pull_request.user.login instead so maintainer-triggered events on Dependabot PRs are not skipped." >&2
  exit 1
fi

echo "✓ dependabot auto-merge workflow regression checks passed"
