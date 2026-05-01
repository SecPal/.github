#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_SCRIPT="$REPO_ROOT/scripts/polyscope-rollout.py"
INSTALL_SCRIPT="$REPO_ROOT/scripts/install-polyscope-rollout.sh"

workspace="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-rollout.XXXXXX")"
trap 'rm -rf "$workspace"' EXIT

workspace_root="$workspace/SecPal"
home_dir="$workspace/home"
mkdir -p "$workspace_root" "$home_dir"

create_repo() {
    local repo_name="$1"
    local copilot_body="$2"
    local focus_filename="$3"
    local focus_body="$4"

    local repo_dir="$workspace_root/$repo_name"
    mkdir -p "$repo_dir/.github/instructions" "$repo_dir/.git/info"
    printf '%s\n' "$copilot_body" > "$repo_dir/.github/copilot-instructions.md"
    printf '%s\n' "$focus_body" > "$repo_dir/.github/instructions/$focus_filename"
    : > "$repo_dir/.git/info/exclude"
}

write_repo_runtime_files() {
    python3 - <<'PY' "$workspace_root"
import json
import sys
from pathlib import Path

workspace_root = Path(sys.argv[1])

(workspace_root / "api" / "composer.json").write_text("{}\n")
(workspace_root / "api" / "artisan").write_text("#!/usr/bin/env php\n")

(workspace_root / ".github" / "scripts").mkdir(parents=True, exist_ok=True)
(workspace_root / ".github" / "scripts" / "preflight.sh").write_text("#!/usr/bin/env bash\n")

package_scripts = {
    "frontend": {
        "build": "vite build",
        "lint": "eslint .",
        "typecheck": "tsc --noEmit",
        "test:watch": "vitest",
    },
    "contracts": {
        "validate": "redocly lint docs/openapi.yaml",
        "lint": "redocly lint docs/openapi.yaml",
        "format:check": "prettier --check '**/*.{md,yml,yaml,json}'",
    },
    "android": {
        "lint": "eslint .",
        "typecheck": "tsc --noEmit",
        "test:run": "vitest run --bail=1",
        "native:verify": "test -f android/settings.gradle",
    },
    "secpal.app": {
        "build": "astro build",
        "check": "astro check",
        "lint": "eslint .",
        "test": "node --test tests/**/*.mjs",
    },
    "changelog": {
        "build": "next build",
        "check": "tsc --noEmit",
        "lint": "eslint .",
        "csp:check": "node scripts/generate-csp.mjs --check",
    },
    ".github": {
        "copilot:review:scan": "./scripts/copilot-review-tool.sh scan",
    },
}

for repo_name, scripts in package_scripts.items():
    repo_dir = workspace_root / repo_name
    package_json = {
        "name": repo_name.replace(".", "-"),
        "private": True,
        "scripts": scripts,
    }
    package_lock = {
        "name": repo_name.replace(".", "-"),
        "lockfileVersion": 3,
        "requires": True,
        "packages": {},
    }
    (repo_dir / "package.json").write_text(json.dumps(package_json, indent=2) + "\n")
    (repo_dir / "package-lock.json").write_text(json.dumps(package_lock, indent=2) + "\n")
PY
}

assert_rollout_rejects_invalid_local_config() {
    local source_script="$1"
    local old_text="$2"
    local new_text="$3"
    local expected_error="$4"
    local script_basename
    local script_copy
    local db_copy="$workspace/invalid-polyscope.db"
    local nginx_copy="$workspace/invalid-preview.secpal.dev.conf"
    local summary_copy="$workspace/invalid-summary.json"

    script_basename="$(basename "$source_script" .py)"
    script_copy="$workspace/${script_basename}-invalid.py"

    cp "$source_script" "$script_copy"

    python3 - <<'PY' "$script_copy" "$old_text" "$new_text"
import sys
from pathlib import Path

script_path = Path(sys.argv[1])
old_text = sys.argv[2]
new_text = sys.argv[3].encode("utf-8").decode("unicode_escape")
contents = script_path.read_text()

if old_text not in contents:
    raise SystemExit(f"mutation marker not found: {old_text}")

script_path.write_text(contents.replace(old_text, new_text, 1))
PY

cp "$db_path" "$db_copy"

if python3 "$script_copy" \
        --workspace-root "$workspace_root" \
        --db-path "$db_copy" \
        --repo-state-file "$repos_json" \
        --nginx-output "$nginx_copy" \
        --summary-output "$summary_copy" \
        >/tmp/polyscope-rollout-invalid.stdout 2>/tmp/polyscope-rollout-invalid.stderr; then
        echo "invalid Polyscope local_config mutation should have failed" >&2
        exit 1
    fi

    grep -q "$expected_error" /tmp/polyscope-rollout-invalid.stderr
}

common_header='<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: AGPL-3.0-or-later
-->'

create_repo "api" "$common_header

# API Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD is mandatory for behavior and code changes.
- Update CHANGELOG.md in the same change set for real changes.
- Never use bypasses such as --no-verify or force-push.

## Issue And PR Discipline

- The first PR state must be draft.
- Use --body-file when creating or editing multi-line PR bodies.

## Required Validation

- the active branch and PR scope still address exactly one topic
- TDD happened for any behavior or code change: the relevant Pest test failed first and now passes
- the smallest relevant Pest coverage for the touched area passed
- vendor/bin/pint --dirty ran after PHP changes
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "php-laravel.instructions.md" "---
name: Laravel PHP Rules
applyTo: '**/*.php'
---

# Laravel PHP Rules

- Use Form Requests for validation and services for business logic.
- Add or update the smallest relevant Pest test for each PHP change, then run the affected tests.
- Use vendor/bin/pint --dirty after changes.
"

create_repo "frontend" "$common_header

# Frontend Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD is mandatory.
- Keep one topic per change.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- TDD happened: the relevant test failed first and now passes
- the smallest relevant validation for the touched area passed: tests, typecheck, and lint when applicable
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "react-typescript.instructions.md" "---
name: React TypeScript Rules
applyTo: 'src/**/*.tsx'
---

# React TypeScript Rules

- Preserve strict TypeScript and generated API types.
- Test user-visible behavior with Testing Library.
- Keep load, action, and destructive-flow error state separate.
"

create_repo "contracts" "$common_header

# Contracts Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD and contract-first discipline are mandatory.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- contract-first and test-first behavior happened
- the relevant contract validation passed, including npm run lint and formatting when needed
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "openapi.instructions.md" "---
name: OpenAPI Contract Rules
applyTo: 'docs/openapi.yaml'
---

# OpenAPI Contract Rules

- Use OpenAPI 3.1 syntax only.
- Reuse components with \$ref.
- Run the relevant Redocly validation and formatting after edits.
"

create_repo "android" "$common_header

# Android Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD is mandatory for behavior and code changes.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- the smallest relevant validation for the touched area passed: tests, typecheck, and lint when applicable
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "react-capacitor.instructions.md" "---
name: React Capacitor Rules
applyTo: 'src/**/*.tsx'
---

# React Capacitor Rules

- Keep Android enterprise implementation details behind explicit bridge boundaries.
- Verify bridge-facing behavior with focused unit tests and mocks.
- For bridge or listener fixes, assert both registration arguments and returned handle behavior.
"

create_repo "secpal.app" "$common_header

# secpal.app Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- Validate-first.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- the smallest relevant validation passed for the touched area: formatting, lint, typecheck, and build when applicable
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "astro-static.instructions.md" "---
name: Astro Static Site Rules
applyTo: 'src/**/*.astro'
---

# Astro Static Site Rules

- Prefer semantic HTML, accessible landmarks, and keyboard-safe interactions.
- Keep client-side JavaScript minimal.
- Run formatting, lint, typecheck, and build.
"

create_repo "changelog" "$common_header

# Changelog Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- Validate-first.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- the smallest relevant validation passed for the touched area: formatting, lint, typecheck, and build when applicable
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "nextjs-changelog.instructions.md" "---
name: Next.js Changelog Rules
applyTo: 'src/**/*.tsx'
---

# Next.js Changelog Rules

- Keep client-side JavaScript minimal.
- Do not introduce server actions.
- Run npm run build as the primary validation after source changes.
"

create_repo ".github" "$common_header

# Org Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD is mandatory for behavior, automation, or executable policy changes.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- TDD happened where executable behavior or validation changed
- the smallest relevant validation for the touched area passed, and ./scripts/preflight.sh ran for substantial governance or workflow changes
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix PRs as hints, not proof.
- Before merge, prove the defect with a failing test, a reproducible defect, or a stated invariant.
- Green CI alone is not enough for AI-generated changes.
" "github-workflows.instructions.md" "---
name: GitHub Workflow Rules
applyTo: '.github/workflows/**/*.yml'
---

# GitHub Workflow Rules

- Always set timeout-minutes on every job.
- Set explicit permissions on every workflow.
- Pin external actions to a specific version.
"

write_repo_runtime_files

db_path="$workspace/polyscope.db"
repos_json="$workspace/repos.json"
nginx_output="$workspace/preview.secpal.dev.conf"
summary_output="$workspace/summary.json"

python3 - <<'PY' "$db_path" "$repos_json" "$workspace_root"
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
repos_json = Path(sys.argv[2])
workspace_root = Path(sys.argv[3])

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('create table repositories (id text primary key, name text not null, path text not null, created_at text, base_branch text, default_model text, merge_prompt text, pr_prompt text, draft_pr_prompt text, merge_and_push_prompt text, worktree_base_from_origin integer, github_assign_self_enabled integer default 0 not null, review_model text, review_prompt text)')
cur.execute('create table repository_links (repo_id text not null, linked_repo_id text not null, created_at text default (datetime(\'now\')) not null, primary key (repo_id, linked_repo_id))')

repo_state = {
    'api': {'id': 'api12345', 'name': 'SecPal/api', 'path': str(workspace_root / 'api')},
    'frontend': {'id': 'fe123456', 'name': 'SecPal/frontend', 'path': str(workspace_root / 'frontend')},
    'contracts': {'id': 'co123456', 'name': 'SecPal/contracts', 'path': str(workspace_root / 'contracts')},
    'android': {'id': 'an123456', 'name': 'SecPal/android', 'path': str(workspace_root / 'android')},
    'secpal.app': {'id': 'sa123456', 'name': 'SecPal/secpal.app', 'path': str(workspace_root / 'secpal.app')},
    'changelog': {'id': 'ch123456', 'name': 'SecPal/changelog', 'path': str(workspace_root / 'changelog')},
    '.github': {'id': 'gh123456', 'name': 'SecPal/.github', 'path': str(workspace_root / '.github')},
}

for repo in repo_state.values():
    cur.execute('insert into repositories (id, name, path, created_at, base_branch, github_assign_self_enabled) values (?, ?, ?, datetime(\'now\'), ?, ?)', (repo['id'], repo['name'], repo['path'], 'main', 0))

conn.commit()
conn.close()
repos_json.write_text(json.dumps(repo_state, indent=2))
PY

python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$summary_output" \
    > /dev/null

grep -q 'api-{{folder}}.preview.secpal.dev' "$workspace_root/api/polyscope.local.json"
grep -q 'Apply the current SecPal instructions from ' "$workspace_root/api/polyscope.local.json"
grep -q 'react-typescript.instructions.md before taking action' "$workspace_root/frontend/polyscope.local.json"
grep -q 'polyscope.local.json' "$workspace_root/api/.git/info/exclude"
if grep -q 'npm install' "$workspace_root/api/polyscope.local.json"; then
    echo "api polyscope config must not run npm install" >&2
    exit 1
fi

if grep -q 'npm run build' "$workspace_root/api/polyscope.local.json"; then
    echo "api polyscope config must not run npm build" >&2
    exit 1
fi

if grep -q 'node_modules' "$workspace_root/api/polyscope.local.json"; then
    echo "api polyscope config must not reference node_modules" >&2
    exit 1
fi

grep -q 'server_name ~^(?<repo>api|frontend|secpal-app|changelog)-' "$nginx_output"
grep -q "/home/secpal/.polyscope/clones/api12345/\\\$workspace" "$nginx_output"

npx --yes prettier --check \
    "$workspace_root/api/polyscope.local.json" \
    "$workspace_root/frontend/polyscope.local.json" \
    "$workspace_root/contracts/polyscope.local.json" \
    "$workspace_root/android/polyscope.local.json" \
    "$workspace_root/secpal.app/polyscope.local.json" \
    "$workspace_root/changelog/polyscope.local.json" \
    "$workspace_root/.github/polyscope.local.json" \
    >/dev/null

python3 - <<'PY' "$db_path" "$summary_output"
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])

conn = sqlite3.connect(db_path)
cur = conn.cursor()

api_prompt = cur.execute('select review_prompt from repositories where id = ?', ('api12345',)).fetchone()[0]
frontend_prompt = cur.execute('select pr_prompt from repositories where id = ?', ('fe123456',)).fetchone()[0]
links = cur.execute('select repo_id, linked_repo_id from repository_links order by repo_id, linked_repo_id').fetchall()

assert 'api/.github/copilot-instructions.md' in api_prompt
assert 'php-laravel.instructions.md' in api_prompt
assert 'Run git status --short --branch before any write action.' in api_prompt
assert 'Use Form Requests for validation and services for business logic.' in api_prompt
assert 'Write a concise English PR body for SecPal/frontend.' in frontend_prompt
assert ('api12345', 'an123456') in links
assert ('api12345', 'co123456') in links
assert ('api12345', 'fe123456') in links
assert ('sa123456', 'ch123456') in links

summary = json.loads(summary_path.read_text())
assert summary['repositories']['api']['preview_prefix'] == 'api'
assert summary['repositories']['contracts']['preview_prefix'] is None
assert summary['repositories']['.github']['linked_repositories'] == []
PY

assert_rollout_rejects_invalid_local_config \
    "$PYTHON_SCRIPT" \
    '"test -d vendor || composer install",' \
    '"test -d vendor || composer install",\n                    "test -d node_modules || npm ci",' \
    "api polyscope config references npm without a package.json at the repo root"

assert_rollout_rejects_invalid_local_config \
    "$PYTHON_SCRIPT" \
    '"command": "npm run copilot:review:scan"' \
    '"command": "npm run missing:scan"' \
    ".github polyscope config references missing npm script 'missing:scan'"

fake_bin_dir="$workspace/fake-bin"
fake_unit_dir="$workspace/fake-units"
fake_systemctl_dir="$workspace/fake-systemctl"
fake_systemctl_log="$workspace/systemctl.log"
mkdir -p "$fake_bin_dir" "$fake_unit_dir" "$fake_systemctl_dir"

cat >"$fake_systemctl_dir/systemctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
exit 0
STUB
chmod +x "$fake_systemctl_dir/systemctl"

env HOME="$home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir"

test -L "$fake_bin_dir/polyscope-secpal-rollout.py"
test -x "$fake_bin_dir/polyscope-secpal-rollout.py"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root ' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q '/api/.github/copilot-instructions.md' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/polyscope-rollout\.py$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -q 'daemon-reload' "$fake_systemctl_log"
grep -q 'enable --now polyscope-rollout-sync.path' "$fake_systemctl_log"
grep -q 'start polyscope-rollout-sync.service' "$fake_systemctl_log"
