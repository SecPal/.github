#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REAPER="$REPO_ROOT/scripts/reap-polyscope-clones.py"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-clone-reaper.XXXXXX")"
active_pid=""
trap '[[ -z "$active_pid" ]] || kill "$active_pid" 2>/dev/null || true; rm -rf "$workspace"' EXIT

polyscope_home="$workspace/.polyscope"
clone_root="$polyscope_home/clones"
mkdir -p "$clone_root"

python3 - <<'PY' "$polyscope_home" "$clone_root"
import sqlite3
import sys
from pathlib import Path

home = Path(sys.argv[1])
clones = Path(sys.argv[2])
conn = sqlite3.connect(home / 'polyscope.db')
conn.executescript('''
CREATE TABLE repositories (id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL);
CREATE TABLE worktrees (id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, branch TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL);
''')
conn.execute('INSERT INTO repositories VALUES (?, ?, ?)', ('active-repo', 'active', '/tmp/active'))
conn.execute('INSERT INTO repositories VALUES (?, ?, ?)', ('inactive-repo', 'inactive', '/tmp/inactive'))
conn.execute('INSERT INTO repositories VALUES (?, ?, ?)', ('path-id', 'path', str(clones / 'registered-path-root')))
active = clones / 'active-repo' / 'workspace'
active.mkdir(parents=True)
conn.execute('INSERT INTO worktrees VALUES (?, ?, ?, ?, ?)', ('active', 'active-repo', 'main', str(active), 'active'))
inactive = clones / 'inactive-repo' / 'workspace'
inactive.mkdir(parents=True)
conn.execute('INSERT INTO worktrees VALUES (?, ?, ?, ?, ?)', ('inactive', 'inactive-repo', 'old', str(inactive), 'removed'))
direct = clones / 'direct-worktree'
direct.mkdir()
conn.execute('INSERT INTO worktrees VALUES (?, ?, ?, ?, ?)', ('direct', 'active-repo', 'direct', str(direct), 'active'))
conn.commit()
conn.close()
PY

mkdir -p "$clone_root/orphan-old/node_modules/cache" "$clone_root/orphan-young" "$clone_root/orphan-lock/.git" "$clone_root/orphan-busy"
mkdir -p "$clone_root/registered-path-root"
outside_root="$workspace/outside-clone-root"
mkdir -p "$outside_root"
ln -s "$outside_root" "$clone_root/external-link"
printf 'payload\n' > "$clone_root/orphan-old/node_modules/cache/file"
touch "$clone_root/orphan-old/yarn.lock"
python3 - <<'PY' "$clone_root/orphan-old" "$clone_root/inactive-repo" "$clone_root/orphan-lock" "$clone_root/orphan-busy" "$clone_root/registered-path-root" "$clone_root/direct-worktree"
import os
import sys
import time

mtime = time.time() - 10 * 24 * 60 * 60
for value in sys.argv[1:]:
    os.utime(value, (mtime, mtime))
PY
touch "$clone_root/orphan-lock/.git/index.lock"

# A process whose current directory is inside a candidate must prevent deletion.
(cd "$clone_root/orphan-busy" && sleep 30) &
active_pid=$!

dry_run_output="$(python3 "$REAPER" --polyscope-home "$polyscope_home" --grace-period 7d --dry-run --json)"
python3 - <<'PY' "$dry_run_output" "$clone_root"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
clones = Path(sys.argv[2])
assert report['removed'] == []
assert report['would_remove'] == [str(clones / 'orphan-old')]
assert report['skipped']['active'] == [
    str(clones / 'active-repo'),
    str(clones / 'direct-worktree'),
    str(clones / 'inactive-repo'),
    str(clones / 'registered-path-root'),
]
assert report['skipped']['grace_period'] == [str(clones / 'orphan-young')]
assert report['skipped']['lock'] == [str(clones / 'orphan-lock')]
assert report['skipped']['process'] == [str(clones / 'orphan-busy')]
assert report['skipped']['unsafe'] == [str(clones / 'external-link')]
assert report['reclaimed_bytes'] > 0
PY

[[ -d "$clone_root/orphan-old" ]] || { echo 'dry run removed a clone root' >&2; exit 1; }

run_output="$(python3 "$REAPER" --polyscope-home "$polyscope_home" --grace-period 7d --json)"
python3 - <<'PY' "$run_output" "$clone_root"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
clones = Path(sys.argv[2])
assert report['removed'] == [str(clones / 'orphan-old')]
assert report['would_remove'] == []
assert report['reclaimed_bytes'] > 0
PY

[[ ! -e "$clone_root/orphan-old" ]] || { echo 'orphan clone root was not removed' >&2; exit 1; }
[[ -d "$clone_root/active-repo" && -d "$clone_root/direct-worktree" && -d "$clone_root/inactive-repo" && -d "$clone_root/orphan-young" && -d "$clone_root/orphan-lock" && -d "$clone_root/orphan-busy" && -d "$clone_root/registered-path-root" && -d "$outside_root" ]] || {
    echo 'reaper removed a protected clone root' >&2
    exit 1
}

# A repository registered after the initial allowlist read must still prevent
# deletion at the final destructive boundary.
mkdir -p "$clone_root/racing-repo/workspace"
python3 - <<'PY' "$clone_root/racing-repo"
import os
import sys
import time

mtime = time.time() - 10 * 24 * 60 * 60
os.utime(sys.argv[1], (mtime, mtime))
PY
python3 - <<'PY' "$REAPER" "$polyscope_home" "$clone_root"
import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location('clone_reaper', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
home = Path(sys.argv[2])
clones = Path(sys.argv[3])
original_process_check = module.has_active_process
registered = False

def register_during_scan(root):
    global registered
    if root.name == 'racing-repo' and not registered:
        with sqlite3.connect(home / 'polyscope.db') as conn:
            conn.execute('INSERT INTO repositories VALUES (?, ?, ?)', ('racing-repo', 'racing', '/tmp/racing'))
        registered = True
    return original_process_check(root)

module.has_active_process = register_during_scan
report = module.reap(argparse.Namespace(
    polyscope_home=str(home), clone_root=str(clones), grace_period=7 * 24 * 60 * 60,
    dry_run=False, json=True,
))
assert (clones / 'racing-repo').is_dir(), report
assert str(clones / 'racing-repo') not in report['removed'], report
PY

# Older Polyscope databases have no worktree status column. Their registered
# worktrees must still be protected instead of disabling scheduled cleanup.
legacy_home="$workspace/legacy/.polyscope"
legacy_root="$legacy_home/clones"
mkdir -p "$legacy_root/legacy-worktree" "$legacy_root/legacy-orphan"
python3 - <<'PY' "$legacy_home" "$legacy_root"
import os
import sqlite3
import sys
import time
from pathlib import Path

home = Path(sys.argv[1])
root = Path(sys.argv[2])
conn = sqlite3.connect(home / 'polyscope.db')
conn.executescript('''
CREATE TABLE repositories (id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL);
CREATE TABLE worktrees (id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, branch TEXT NOT NULL, path TEXT NOT NULL);
''')
conn.execute('INSERT INTO repositories VALUES (?, ?, ?)', ('legacy-repo', 'legacy', '/tmp/legacy'))
conn.execute('INSERT INTO worktrees VALUES (?, ?, ?, ?)', ('legacy', 'legacy-repo', 'main', str(root / 'legacy-worktree')))
conn.commit()
conn.close()
mtime = time.time() - 10 * 24 * 60 * 60
for path in (root / 'legacy-worktree', root / 'legacy-orphan'):
    os.utime(path, (mtime, mtime))
PY
legacy_output="$(python3 "$REAPER" --polyscope-home "$legacy_home" --dry-run --json)"
python3 - <<'PY' "$legacy_output" "$legacy_root"
import json
import sys
from pathlib import Path

report = json.loads(sys.argv[1])
root = Path(sys.argv[2])
assert report['skipped']['active'] == [str(root / 'legacy-worktree')]
assert report['would_remove'] == [str(root / 'legacy-orphan')]
PY

# A configured clone root must be absolute and must not permit cleanup elsewhere.
set +e
outside_output="$(python3 "$REAPER" --polyscope-home "$polyscope_home" --clone-root relative --dry-run 2>&1)"
outside_status=$?
set -e
[[ $outside_status -eq 2 ]] || { echo "expected invalid clone root to fail: $outside_output" >&2; exit 1; }
