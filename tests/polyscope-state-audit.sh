#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AUDIT_SCRIPT="$REPO_ROOT/scripts/audit-polyscope-state.py"

if [[ ! -x "$AUDIT_SCRIPT" ]]; then
  echo "Expected executable audit script at $AUDIT_SCRIPT" >&2
  exit 1
fi

workspace="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-state-audit.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

polyscope_home="$workspace/.polyscope"
workspace_root="$workspace/SecPal"
mkdir -p "$polyscope_home/clones" "$workspace_root/api" "$workspace_root/frontend"

printf '{"preview":{"url":"https://api-{{folder}}.preview.secpal.dev"}}\n' > "$workspace_root/api/polyscope.local.json"
printf '{"preview":{"url":"https://frontend-{{folder}}.preview.secpal.dev"}}\n' > "$workspace_root/frontend/polyscope.local.json"

python3 - <<'PY' "$polyscope_home" "$workspace_root"
import sqlite3
import sys
from pathlib import Path

polyscope_home = Path(sys.argv[1])
workspace_root = Path(sys.argv[2])
db_path = polyscope_home / 'polyscope.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript(
    '''
    CREATE TABLE repositories (
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        path TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
        base_branch TEXT DEFAULT 'main' NOT NULL
    );

    CREATE TABLE worktrees (
        id TEXT PRIMARY KEY NOT NULL,
        repo_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        path TEXT NOT NULL,
        status TEXT DEFAULT 'active' NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
        FOREIGN KEY (repo_id) REFERENCES repositories(id)
    );
    '''
)

cur.executemany(
    'INSERT INTO repositories (id, name, path, base_branch) VALUES (?, ?, ?, ?)',
    [
        ('api11111', 'SecPal/api', str(workspace_root / 'api'), 'main'),
        ('frontend2', 'SecPal/frontend', str(workspace_root / 'frontend'), 'main'),
    ],
)

tracked = polyscope_home / 'clones' / 'api11111' / 'tracked-worktree'
tracked.mkdir(parents=True)
cur.execute(
    'INSERT INTO worktrees (id, repo_id, branch, path, status) VALUES (?, ?, ?, ?, ?)',
    ('wt1', 'api11111', 'feature/tracked', str(tracked), 'active'),
)

conn.commit()
conn.close()
PY

git init -q "$polyscope_home/clones/api11111/tracked-worktree"
cp "$workspace_root/api/polyscope.local.json" "$polyscope_home/clones/api11111/tracked-worktree/polyscope.local.json"
mkdir -p "$polyscope_home/clones/api11111/tracked-worktree/.git/info"
printf 'polyscope.local.json\n' > "$polyscope_home/clones/api11111/tracked-worktree/.git/info/exclude"

mkdir -p "$polyscope_home/clones/api11111/unregistered-worktree"
git init -q "$polyscope_home/clones/api11111/unregistered-worktree"

mkdir -p "$polyscope_home/clones/orphan9999/invalid-stub"

printf 'backup one\n' > "$polyscope_home/polyscope.db.backup-20260601T000000Z"
printf 'backup two\n' > "$polyscope_home/polyscope.db.backup-20260602T000000Z"
printf 'backup three\n' > "$polyscope_home/polyscope.db.backup-20260603T000000Z"

set +e
dirty_output="$(python3 "$AUDIT_SCRIPT" --polyscope-home "$polyscope_home" --backup-retention 2 --json 2>&1)"
dirty_status=$?
set -e

if [[ $dirty_status -ne 1 ]]; then
  echo "Expected dirty Polyscope fixture to exit with status 1, got $dirty_status" >&2
  echo "$dirty_output" >&2
  exit 1
fi

python3 - <<'PY' "$dirty_output" "$polyscope_home" "$workspace_root"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
polyscope_home = Path(sys.argv[2])
workspace_root = Path(sys.argv[3])

assert report['orphan_clone_roots'] == [str(polyscope_home / 'clones' / 'orphan9999')]
assert report['invalid_clone_worktrees'] == [str(polyscope_home / 'clones' / 'orphan9999' / 'invalid-stub')]
assert report['unregistered_git_worktrees'] == [str(polyscope_home / 'clones' / 'api11111' / 'unregistered-worktree')]
assert report['excess_db_backups'] == [str(polyscope_home / 'polyscope.db.backup-20260601T000000Z')]
assert report['repos_missing_clone_roots'] == [
    {
        'repo_id': 'frontend2',
        'repo_name': 'SecPal/frontend',
        'repo_path': str(workspace_root / 'frontend'),
        'clone_root': str(polyscope_home / 'clones' / 'frontend2'),
    }
]
assert report['missing_registered_worktrees'] == []
assert report['worktrees_missing_repositories'] == []
assert report['missing_clone_local_configs'] == []
assert report['worktree_config_mismatches'] == []
assert report['missing_worktree_excludes'] == []
PY

mkdir -p "$polyscope_home/clones/frontend2"
rm -rf "$polyscope_home/clones/orphan9999"
rm -rf "$polyscope_home/clones/api11111/unregistered-worktree"
rm -f "$polyscope_home/polyscope.db.backup-20260601T000000Z"

clean_output="$(python3 "$AUDIT_SCRIPT" --polyscope-home "$polyscope_home" --backup-retention 2 --json)"

python3 - <<'PY' "$clean_output"
import json
import sys

report = json.loads(sys.argv[1])

for key, value in report.items():
    if isinstance(value, list):
        assert value == [], (key, value)
PY

printf 'backup four\n' > "$polyscope_home/polyscope.db.backup-20260604T000000Z"
printf 'backup five\n' > "$polyscope_home/polyscope.db.backup-20260605T000000Z"

set +e
zero_retention_output="$(python3 "$AUDIT_SCRIPT" --polyscope-home "$polyscope_home" --backup-retention 0 --json 2>&1)"
zero_retention_status=$?
set -e

if [[ $zero_retention_status -ne 1 ]]; then
    echo "Expected zero-retention backup audit to exit with status 1, got $zero_retention_status" >&2
    echo "$zero_retention_output" >&2
    exit 1
fi

python3 - <<'PY' "$zero_retention_output" "$polyscope_home"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
polyscope_home = Path(sys.argv[2])

assert report['excess_db_backups'] == [
        str(polyscope_home / 'polyscope.db.backup-20260602T000000Z'),
        str(polyscope_home / 'polyscope.db.backup-20260603T000000Z'),
        str(polyscope_home / 'polyscope.db.backup-20260604T000000Z'),
        str(polyscope_home / 'polyscope.db.backup-20260605T000000Z'),
]
PY

broken_worktree="$workspace/missing-repo-worktree"
mkdir -p "$broken_worktree"

python3 - <<'PY' "$polyscope_home" "$broken_worktree"
import sqlite3
import sys
from pathlib import Path

polyscope_home = Path(sys.argv[1])
broken_worktree = Path(sys.argv[2])
conn = sqlite3.connect(polyscope_home / 'polyscope.db')
cur = conn.cursor()
cur.execute(
    'INSERT INTO worktrees (id, repo_id, branch, path, status) VALUES (?, ?, ?, ?, ?)',
    ('wt-missing-repo', 'missing99', 'feature/missing-repo', str(broken_worktree), 'active'),
)
conn.commit()
conn.close()
PY

set +e
missing_repo_output="$(python3 "$AUDIT_SCRIPT" --polyscope-home "$polyscope_home" --backup-retention 10 --json 2>&1)"
missing_repo_status=$?
set -e

if [[ $missing_repo_status -ne 1 ]]; then
    echo "Expected missing-repo audit to exit with status 1, got $missing_repo_status" >&2
    echo "$missing_repo_output" >&2
    exit 1
fi

python3 - <<'PY' "$missing_repo_output" "$broken_worktree"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
broken_worktree = Path(sys.argv[2])

assert report['worktrees_missing_repositories'] == [
    {
        'repo_id': 'missing99',
        'branch': 'feature/missing-repo',
        'path': str(broken_worktree),
        'status': 'active',
    }
]
PY

# === Scenario: worktree-level findings ===
# Covers missing_registered_worktrees, missing_clone_local_configs,
# worktree_config_mismatches, missing_worktree_excludes plus proves
# that exclude resolution follows the gitdir pointer for linked worktrees.

poly2_home="$workspace/poly2/.polyscope"
poly2_workspace="$workspace/poly2/SecPal"
mkdir -p "$poly2_home/clones/api22222" "$poly2_workspace/api"

printf '{"preview":{"url":"https://api-{{folder}}.preview.secpal.dev"}}\n' > "$poly2_workspace/api/polyscope.local.json"

python3 - <<'PY' "$poly2_home" "$poly2_workspace"
import sqlite3
import sys
from pathlib import Path

poly2_home = Path(sys.argv[1])
poly2_workspace = Path(sys.argv[2])
db_path = poly2_home / 'polyscope.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.executescript(
    '''
    CREATE TABLE repositories (
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        path TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
        base_branch TEXT DEFAULT 'main' NOT NULL
    );

    CREATE TABLE worktrees (
        id TEXT PRIMARY KEY NOT NULL,
        repo_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        path TEXT NOT NULL,
        status TEXT DEFAULT 'active' NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP NOT NULL,
        FOREIGN KEY (repo_id) REFERENCES repositories(id)
    );
    '''
)

cur.execute(
    'INSERT INTO repositories (id, name, path, base_branch) VALUES (?, ?, ?, ?)',
    ('api22222', 'SecPal/api', str(poly2_workspace / 'api'), 'main'),
)

clone_root = poly2_home / 'clones' / 'api22222'
entries = [
    ('wt-disappear', 'feature/disappear', clone_root / 'disappeared'),
    ('wt-no-cfg',    'feature/no-cfg',    clone_root / 'no-config'),
    ('wt-drift',     'feature/drift',     clone_root / 'drift'),
    ('wt-no-excl',   'feature/no-excl',   clone_root / 'no-exclude'),
    ('wt-linked',    'feature/linked',    clone_root / 'linked'),
]
cur.executemany(
    'INSERT INTO worktrees (id, repo_id, branch, path, status) VALUES (?, ?, ?, ?, ?)',
    [(wid, 'api22222', branch, str(path), 'active') for wid, branch, path in entries],
)

conn.commit()
conn.close()
PY

# wt-disappear: intentionally not created on disk -> missing_registered_worktrees

# wt-no-cfg: dir + git init, no polyscope.local.json copied -> missing_clone_local_configs
# (audit then short-circuits exclude check because worktree_config branch already failed)
git init -q "$poly2_home/clones/api22222/no-config"

# wt-drift: config differs from repo config -> worktree_config_mismatches; exclude is fine
git init -q "$poly2_home/clones/api22222/drift"
printf '{"preview":{"url":"https://drift.preview.secpal.dev"}}\n' > "$poly2_home/clones/api22222/drift/polyscope.local.json"
printf 'polyscope.local.json\n' > "$poly2_home/clones/api22222/drift/.git/info/exclude"

# wt-no-excl: config matches but exclude entry missing -> missing_worktree_excludes
git init -q "$poly2_home/clones/api22222/no-exclude"
cp "$poly2_workspace/api/polyscope.local.json" "$poly2_home/clones/api22222/no-exclude/polyscope.local.json"
printf 'unrelated-entry\n' > "$poly2_home/clones/api22222/no-exclude/.git/info/exclude"

# wt-linked: real linked worktree (.git is a file) - proves gitdir is resolved
# before reading info/exclude. The linked gitdir lives outside the clones tree
# so the clone-scan loop does not see it as a clone subdir.
main_repo="$workspace/poly2/main-repo"
git init -q "$main_repo"
git -C "$main_repo" -c user.email=t@example.com -c user.name=tester commit -q --allow-empty -m bootstrap
git -C "$main_repo" worktree add --quiet -b feature/linked "$poly2_home/clones/api22222/linked"
cp "$poly2_workspace/api/polyscope.local.json" "$poly2_home/clones/api22222/linked/polyscope.local.json"
linked_gitdir="$(git -C "$poly2_home/clones/api22222/linked" rev-parse --absolute-git-dir)"
mkdir -p "$linked_gitdir/info"
printf 'polyscope.local.json\n' > "$linked_gitdir/info/exclude"

set +e
worktree_findings_output="$(python3 "$AUDIT_SCRIPT" --polyscope-home "$poly2_home" --backup-retention 10 --json 2>&1)"
worktree_findings_status=$?
set -e

if [[ $worktree_findings_status -ne 1 ]]; then
    echo "Expected worktree-findings scenario to exit with status 1, got $worktree_findings_status" >&2
    echo "$worktree_findings_output" >&2
    exit 1
fi

python3 - <<'PY' "$worktree_findings_output" "$poly2_home"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
clones = Path(sys.argv[2]) / 'clones' / 'api22222'

linked_path = str(clones / 'linked')

assert [wt['branch'] for wt in report['missing_registered_worktrees']] == ['feature/disappear']
assert [wt['path']   for wt in report['missing_registered_worktrees']] == [str(clones / 'disappeared')]

assert sorted(report['missing_clone_local_configs']) == [str(clones / 'no-config')]
assert sorted(report['worktree_config_mismatches'])  == [str(clones / 'drift')]
assert sorted(report['missing_worktree_excludes'])   == sorted([
    str(clones / 'no-config'),
    str(clones / 'no-exclude'),
])

# Linked worktree must NOT show up in any worktree-level finding: that proves
# audit resolves the gitdir before reading info/exclude.
for key in ('missing_clone_local_configs', 'worktree_config_mismatches', 'missing_worktree_excludes'):
    assert linked_path not in report[key], (key, report[key])

assert report['worktrees_missing_repositories'] == []
PY
