#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACTIONS="$REPO_ROOT/scripts/secpal-pr-review-actions.py"
INSTALLER="$REPO_ROOT/scripts/install-secpal-pr-review-skill.sh"
FIXTURES="$SCRIPT_DIR/fixtures/secpal-pr-review-actions"
workspace="$(mktemp -d "${TMPDIR:-/tmp}/secpal-pr-review-skill-integration.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

mkdir -p \
  "$workspace/bin" \
  "$workspace/sibling-style/repository"
cp "$FIXTURES/fake-gh.py" "$workspace/bin/gh"
chmod 0700 "$workspace/bin/gh"
export FAKE_ACTION_GH_LOG="$workspace/gh.log"

python3 - "$REPO_ROOT" "$workspace" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
workspace = Path(sys.argv[2])

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

p21 = load("p21_fixture", root / "tests/secpal-pr-review-unit.py")
actions = load("actions_fixture", root / "scripts/secpal-pr-review-actions.py")
snapshot = p21.snapshot()
snapshot["review_threads"] = [p21.thread()]
snapshot = p21.finalize_snapshot(snapshot)
config = p21.config()
config["reviewer_identities"] = []
finding = {
    "logical_finding_id": "finding-001",
    "source_node_ids": ["RC_1"],
    "source_database_ids": [21],
    "source_subitem_id": None,
    "parent_thread_id": "THREAD_1",
    "classification": "VALID_ACTIONABLE",
    "canonical_finding_id": None,
    "disposition": "CORRECTED_AND_VERIFIED",
    "evidence_digest": "1" * 64,
    "test_evidence": ["focused fixture"],
    "commit_sha": p21.HEAD,
}
operation = {
    "operation_id": "reaction-001",
    "logical_finding_id": "finding-001",
    "kind": "REACTION",
    "target_node_id": "RC_1",
    "target_database_id": 21,
    "parent_thread_id": "THREAD_1",
    "expected_current_state": {
        "target_type": "PULL_REQUEST_REVIEW_COMMENT",
        "body_digest": actions.sha256_text("Finding"),
        "is_resolved": False,
        "is_outdated": False,
        "material_misunderstanding": False,
        "invalidity_non_obvious": False,
    },
    "expected_actor_identity": {"login": "aroviqen", "node_id": "USER_1", "database_id": 7},
    "expected_source_actor_identity": {"login": "reviewer", "node_id": "ACTOR_reviewer", "database_id": 7},
    "classification": "VALID_ACTIONABLE",
    "evidence_digest": finding["evidence_digest"],
    "reaction": "THUMBS_UP",
    "reply_body": None,
    "applied_mutation_identity": None,
    "resolution_preconditions": None,
}
session = {
    "state": "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES",
    "state_captures": 1,
    "remediation_cycles": 0,
    "holistic_audits": 0,
    "signed_commits": 0,
    "fast_forward_pushes": 0,
    "evidence_replies": 0,
    "reaction_writes": 0,
    "thread_resolutions": 0,
    "worktree_clean": True,
    "head_matches": True,
    "snapshot_digest_matches": True,
    "unexplained_commit": False,
    "signatures_valid": True,
    "evidence_complete": True,
    "ci_state": "SUCCESS",
    "unresolved_material_finding": False,
    "github_state_safe": True,
    "scope_requires_other_repository": False,
    "late_feedback_detected": False,
    "push_failed": False,
    "mutation_failed": False,
    "actionable_findings": True,
    "merge_ready_evidence": False,
}
plan = {
    "schema_version": "1.0",
    "repository": "SecPal/.github",
    "pull_request_number": 1,
    "snapshot_digest": snapshot["snapshot_digest"],
    "initial_snapshot_digest": snapshot["snapshot_digest"],
    "expected_head_sha": p21.HEAD,
    "created_for_state": "APPLY_JUSTIFIED_REACTIONS_AND_EXCEPTION_REPLIES",
    "cycle_number": 0,
    "session": session,
    "findings": [finding],
    "operations": [operation],
}
for name, value in (("snapshot.json", snapshot), ("config.json", config), ("plan.json", plan)):
    (workspace / name).write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

common=(
  --plan "$workspace/plan.json"
  --snapshot "$workspace/snapshot.json"
  --config "$workspace/config.json"
  --operation-id reaction-001
  --repo SecPal/.github
  --pr 1
  --snapshot-digest "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot_digest"])' "$workspace/snapshot.json")"
  --expected-head aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
)
fake_cli=(python3 "$FIXTURES/fake-actions-cli.py" "$ACTIONS" "$workspace/bin")

"${fake_cli[@]}" inspect-actor >"$workspace/actor.json"
python3 - "$workspace/actor.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report == {
    "actor": {"database_id": 7, "login": "aroviqen", "node_id": "USER_1"},
    "mutation_performed": False,
    "status": "ACTOR_VERIFIED",
}
PY
: >"$workspace/gh.log"

python3 "$ACTIONS" validate-plan \
  --plan "$workspace/plan.json" \
  --snapshot "$workspace/snapshot.json" \
  --config "$workspace/config.json" >"$workspace/validated.json"

"${fake_cli[@]}" react "${common[@]}" >"$workspace/audit.json"
python3 - "$workspace/gh.log" <<'PY'
import json
import sys

calls = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert len(calls) == 1, calls
assert "query CurrentMutationTarget" in next(value.split("=", 1)[1] for value in calls[0] if value.startswith("query="))
PY

"${fake_cli[@]}" react "${common[@]}" --apply >"$workspace/applied.json"
python3 - "$workspace/audit.json" "$workspace/applied.json" <<'PY'
import json
import sys

audit = json.load(open(sys.argv[1], encoding="utf-8"))
applied = json.load(open(sys.argv[2], encoding="utf-8"))
assert audit["status"] == "VALIDATED_NO_MUTATION"
assert applied["status"] == "APPLIED"
assert applied["mutation_identity"] == "REACTION_NEW"
PY

python3 - "$workspace/gh.log" <<'PY'
import json
import sys

calls = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
assert len(calls) == 5, calls
assert "query CurrentMutationTarget" in next(value.split("=", 1)[1] for value in calls[0] if value.startswith("query="))
assert "query CurrentReviewFeedback" in next(value.split("=", 1)[1] for value in calls[1] if value.startswith("query="))
assert "query CurrentReviewFeedback" in next(value.split("=", 1)[1] for value in calls[2] if value.startswith("query="))
assert "query CurrentMutationTarget" in next(value.split("=", 1)[1] for value in calls[3] if value.startswith("query="))
assert calls[4][calls[4].index("--method") + 1] == "POST"
assert calls[4][3] == "repos/SecPal/.github/pulls/comments/21/reactions"
PY

# A failed complete validation identifies the exact registered entry while
# keeping command output secret, invalidating the receipt, and stopping once.
validation_repo="$workspace/validation-repository"
mkdir -p "$validation_repo"
git -C "$validation_repo" init -q -b main
git -C "$validation_repo" config user.name "SecPal Integration Fixture"
git -C "$validation_repo" config user.email "fixture@secpal.dev"
git -C "$validation_repo" remote add origin https://github.com/SecPal/.github.git
printf '#!/bin/sh\nprintf "first\\n" >>"%s"\nprintf "secret=integration-command-output-must-not-leak\\n" >&2\nexit 9\n' \
  "$workspace/validation-runs.log" >"$validation_repo/validation-fail.sh"
printf '#!/bin/sh\nprintf "second\\n" >>"%s"\n' \
  "$workspace/validation-runs.log" >"$validation_repo/validation-must-not-run.sh"
chmod 0700 \
  "$validation_repo/validation-fail.sh" \
  "$validation_repo/validation-must-not-run.sh"
git -C "$validation_repo" add validation-fail.sh validation-must-not-run.sh
git -C "$validation_repo" -c commit.gpgsign=false commit -q -m "test: add validation fixtures"
validation_head="$(git -C "$validation_repo" rev-parse HEAD)"

python3 - "$ACTIONS" "$workspace" "$validation_head" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

helper = Path(sys.argv[1])
workspace = Path(sys.argv[2])
head = sys.argv[3]
spec = importlib.util.spec_from_file_location("validation_actions_fixture", helper)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

entry = module.select_repository(module.load_registry(), "SecPal/.github")
entry["focused_validation"] = []
entry["required_local_validation"] = [
    {
        "argv": ["./validation-fail.sh"],
        "working_directory": ".",
        "purpose": "Run integration failure probe",
    },
    {
        "argv": ["./validation-must-not-run.sh"],
        "working_directory": ".",
        "purpose": "Reject validation retries",
    },
]
entry["manual_gates"] = []
(workspace / "validation-registry.json").write_text(
    json.dumps(
        {"schema_version": "1.0", "repositories": [entry]},
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n",
    encoding="utf-8",
)
reviewed = module.fast_path.StableFeedbackState.from_payload(
    {
        "repository": "SecPal/.github",
        "pull_request_number": 1,
        "head_sha": head,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "pr_state": "OPEN",
        "pull_request_reactions": [],
        "reviews": [],
        "conversation_comments": [],
        "threads": [],
    }
)
(workspace / "validation-reviewed.json").write_text(
    json.dumps(reviewed.to_dict(), sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

set +e
python3 "$ACTIONS" attest-validation \
  --repo SecPal/.github \
  --expected-head "$validation_head" \
  --reviewed-state "$workspace/validation-reviewed.json" \
  --repo-root "$validation_repo" \
  --registry "$workspace/validation-registry.json" \
  --output "$workspace/validation-receipt.json" \
  2>"$workspace/validation-diagnostic.json"
validation_status=$?
set -e
test "$validation_status" -eq 3

python3 - \
  "$workspace/validation-diagnostic.json" \
  "$workspace/validation-receipt.json" \
  "$workspace/validation-runs.log" \
  "$validation_head" <<'PY'
import json
import sys

diagnostic_text = open(sys.argv[1], encoding="utf-8").read()
diagnostic = json.loads(diagnostic_text)
receipt = json.load(open(sys.argv[2], encoding="utf-8"))
runs = open(sys.argv[3], encoding="utf-8").read().splitlines()
assert diagnostic["status"] == "BLOCKED_SECURITY", diagnostic
assert diagnostic["retry_performed"] is False, diagnostic
assert diagnostic["registered_validation_failure"] == {
    "category": "non-zero exit",
    "index": 1,
    "purpose": "Run integration failure probe",
}, diagnostic
assert "integration-command-output" not in diagnostic_text, diagnostic_text
assert "secret=" not in diagnostic_text, diagnostic_text
assert runs == ["first"], runs
assert receipt == {
    "head_sha": sys.argv[4],
    "schema_version": "1.0",
    "status": "VALIDATION_RECEIPT_INVALIDATED",
    "validated_tree_sha": receipt["validated_tree_sha"],
}, receipt
PY

# Installer fixtures 70-79: clean install, idempotency, correct link, wrong-link
# refusal/repair, non-link refusal, parent creation, missing source, direct link,
# sibling-style user discovery and isolated user configuration.
target_root="$workspace/home/.agents/skills"
HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" >"$workspace/install-1.txt"
link="$target_root/secpal-pr-review"
test -L "$link"
test "$(readlink "$link")" = "$REPO_ROOT/.agents/skills/secpal-pr-review"
test "$(readlink -f "$link")" = "$REPO_ROOT/.agents/skills/secpal-pr-review"
HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" >"$workspace/install-2.txt"
test -L "$link"

rm "$link"
ln -s "$workspace/wrong" "$link"
if HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" 2>"$workspace/wrong-link.txt"; then
  echo 'wrong symlink unexpectedly accepted' >&2
  exit 1
fi
HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" --repair >"$workspace/repaired.txt"
test "$(readlink "$link")" = "$REPO_ROOT/.agents/skills/secpal-pr-review"

rm "$link"
printf 'not a symlink\n' >"$link"
if HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" --repair 2>"$workspace/non-link.txt"; then
  echo 'non-symlink unexpectedly overwritten' >&2
  exit 1
fi
rm "$link"

missing_parent="$workspace/new-home/.agents/skills"
HOME="$workspace/new-home" bash "$INSTALLER" --target-root "$missing_parent" >"$workspace/parent.txt"
test -L "$missing_parent/secpal-pr-review"

significant_root="$workspace/shell significant [skills] \$literal"
HOME="$workspace/home" bash "$INSTALLER" --target-root "$significant_root" >"$workspace/significant.txt"
test "$(readlink "$significant_root/secpal-pr-review")" = "$REPO_ROOT/.agents/skills/secpal-pr-review"

portable_bin="$workspace/portable-bin"
portable_root="$workspace/portable-home/.agents/skills"
real_readlink="$(command -v readlink)"
mkdir -p "$portable_bin"
cat >"$portable_bin/readlink" <<EOF
#!/usr/bin/env bash
if [[ "\${1-}" == -f ]]; then
  exit 64
fi
exec "$real_readlink" "\$@"
EOF
chmod +x "$portable_bin/readlink"
PATH="$portable_bin:$PATH" HOME="$workspace/portable-home" \
  bash "$INSTALLER" --target-root "$portable_root" >"$workspace/portable.txt"
test "$(readlink "$portable_root/secpal-pr-review")" = \
  "$REPO_ROOT/.agents/skills/secpal-pr-review"

if HOME="$workspace/home" bash "$INSTALLER" --target-root "$target_root" --source "$workspace/missing" 2>"$workspace/missing-source.txt"; then
  echo 'missing source unexpectedly accepted' >&2
  exit 1
fi

(
  cd "$workspace/sibling-style/repository"
  test -f "$workspace/new-home/.agents/skills/secpal-pr-review/SKILL.md"
)

printf '✓ finite secpal-pr-review skill integration checks passed\n'
