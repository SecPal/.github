#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_SCRIPT="$REPO_ROOT/scripts/polyscope-rollout.py"
INSTALL_SCRIPT="$REPO_ROOT/scripts/install-polyscope-rollout.sh"
PRETTIER_BIN="$REPO_ROOT/node_modules/.bin/prettier"

if [[ ! -x "$PRETTIER_BIN" ]]; then
    (cd "$REPO_ROOT" && npm ci)
fi
if [[ ! -x "$PRETTIER_BIN" ]]; then
    echo "expected pinned Prettier at $PRETTIER_BIN after npm ci" >&2
    exit 1
fi

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
    printf '%s\n' "---
name: Org Shared Rules
applyTo: '**'
---

# Org Shared Rules

- Keep changes repo-local, minimal, and consistent with the repository stack.
- Apply the SecPal domain policy and issue triage rules.
" > "$repo_dir/.github/instructions/org-shared.instructions.md"
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
        "test:e2e:ci": "cross-env CI=true playwright test",
        "test:e2e:staging": "cross-env PLAYWRIGHT_BASE_URL=https://app.secpal.dev playwright test",
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
    local invalid_out
    local invalid_err

    script_basename="$(basename "$source_script" .py)"
    script_copy="$workspace/${script_basename}-invalid.py"
    invalid_out="${script_copy%.py}.stdout"
    invalid_err="${script_copy%.py}.stderr"

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
        >"$invalid_out" 2>"$invalid_err"; then
        echo "invalid Polyscope local_config mutation should have failed" >&2
        exit 1
    fi

    grep -q "$expected_error" "$invalid_err"
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

grep -q 'https://api-{{folder}}.preview.secpal.dev' "$workspace_root/api/polyscope.local.json"
grep -q 'Apply the current SecPal instructions from ' "$workspace_root/api/polyscope.local.json"
grep -q 'org-shared.instructions.md' "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --prepare-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api" "$workspace_root/api/polyscope.local.json"
grep -qF 'php artisan config:clear && php artisan migrate --force && php artisan db:seed --force && php artisan tinker --execute=' "$workspace_root/api/polyscope.local.json"
grep -qF "test@example.com" "$workspace_root/api/polyscope.local.json"
grep -qF 'Preview Only: Refresh DB + E2E User' "$workspace_root/api/polyscope.local.json"
grep -q 'react-typescript.instructions.md before taking action' "$workspace_root/frontend/polyscope.local.json"
grep -q 'https://frontend-{{folder}}.preview.secpal.dev' "$workspace_root/frontend/polyscope.local.json"
grep -q 'https://secpal-app-{{folder}}.preview.secpal.dev' "$workspace_root/secpal.app/polyscope.local.json"
grep -q 'https://changelog-{{folder}}.preview.secpal.dev' "$workspace_root/changelog/polyscope.local.json"
grep -qF '.env.local' "$workspace_root/frontend/polyscope.local.json"
grep -qF "VITE_API_URL=https://api-\${PWD##*/}.preview.secpal.dev npm run build -- --mode preview" "$workspace_root/frontend/polyscope.local.json"
grep -qF "VITE_API_URL=https://api-\${PWD##*/}.preview.secpal.dev npx vite build --watch --mode preview" "$workspace_root/frontend/polyscope.local.json"
grep -q 'npm run test:e2e:ci' "$workspace_root/frontend/polyscope.local.json"
grep -qF "PLAYWRIGHT_BASE_URL=https://frontend-\${PWD##*/}.preview.secpal.dev" "$workspace_root/frontend/polyscope.local.json"
grep -qF "PLAYWRIGHT_API_BASE_URL=https://api-\${PWD##*/}.preview.secpal.dev" "$workspace_root/frontend/polyscope.local.json"
grep -qF 'tests/e2e/smoke.spec.ts --project=chromium --project=mobile-chrome' "$workspace_root/frontend/polyscope.local.json"
grep -qF "TEST_USER_EMAIL=test@example.com TEST_USER_PASSWORD=password PLAYWRIGHT_BASE_URL=https://frontend-\${PWD##*/}.preview.secpal.dev PLAYWRIGHT_API_BASE_URL=https://api-\${PWD##*/}.preview.secpal.dev npx playwright test" "$workspace_root/frontend/polyscope.local.json"
grep -q 'npm run test:e2e:staging' "$workspace_root/frontend/polyscope.local.json"
grep -q 'polyscope.local.json' "$workspace_root/api/.git/info/exclude"
if grep -q 'TEST_USER_EMAIL=test@password\.com' "$workspace_root/frontend/polyscope.local.json"; then
    echo "generated frontend Polyscope preview commands must not use the obsolete test@password.com credential" >&2
    exit 1
fi
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

grep -q 'server_name ~^(?:(?<repo>api|frontend|secpal-app|changelog)-)?(?<workspace>' "$nginx_output"
grep -q "/home/secpal/.polyscope/clones/api12345/\\\$workspace" "$nginx_output"
grep -qF "try_files \$uri @preview_router;" "$nginx_output"
grep -qF "set \$preview_docroot /home/secpal/.polyscope/__missing_preview_docroot__;" "$nginx_output"

if grep -qF "try_files \$uri \$uri/ @preview_router;" "$nginx_output"; then
    echo "preview nginx config must not treat a missing workspace docroot as a directory hit" >&2
    exit 1
fi

if grep -qF '/home/secpal/.polyscope/empty' "$nginx_output"; then
    echo "preview nginx config must not use a real empty directory as the missing-workspace docroot" >&2
    exit 1
fi

api_if_line="$(grep -nF "if (-f \$api_public/index.php) {" "$nginx_output" | head -n 1 | cut -d: -f1)"
frontend_if_line="$(grep -nF "if (-f \$frontend_dist/index.html) {" "$nginx_output" | head -n 1 | cut -d: -f1)"
secpal_app_if_line="$(grep -nF "if (-f \$secpal_app_dist/index.html) {" "$nginx_output" | head -n 1 | cut -d: -f1)"
changelog_if_line="$(grep -nF "if (-f \$changelog_out/index.html) {" "$nginx_output" | head -n 1 | cut -d: -f1)"

test -n "$api_if_line"
test -n "$frontend_if_line"
test -n "$secpal_app_if_line"
test -n "$changelog_if_line"

if (( api_if_line >= frontend_if_line || frontend_if_line >= secpal_app_if_line || secpal_app_if_line >= changelog_if_line )); then
    echo "generic preview precedence must prefer changelog > secpal.app > frontend > api" >&2
    exit 1
fi

"$PRETTIER_BIN" --check \
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
assert 'org-shared.instructions.md' in api_prompt
assert 'php-laravel.instructions.md' in api_prompt
assert 'Run git status --short --branch before any write action.' in api_prompt
assert 'Use Form Requests for validation and services for business logic.' in api_prompt
assert 'Keep changes repo-local, minimal, and consistent with the repository stack.' in api_prompt
assert 'Write a concise English PR body for SecPal/frontend.' in frontend_prompt
assert ('api12345', 'an123456') in links
assert ('api12345', 'co123456') in links
assert ('api12345', 'fe123456') in links
assert ('sa123456', 'ch123456') in links

summary = json.loads(summary_path.read_text())
assert summary['repositories']['api']['preview_prefix'] == 'api'
assert summary['repositories']['frontend']['preview_prefix'] == 'frontend'
assert summary['repositories']['secpal.app']['preview_prefix'] == 'secpal-app'
assert summary['repositories']['changelog']['preview_prefix'] == 'changelog'
assert summary['repositories']['contracts']['preview_prefix'] is None
assert summary['repositories']['api']['focus_instruction_paths'][0].endswith('org-shared.instructions.md')
assert summary['repositories']['.github']['linked_repositories'] == []
PY

provision_log="$workspace/provision.log"
fake_psql_log="$workspace/psql.log"
fake_pg_state="$workspace/postgres-state.json"
fake_exec_dir="$workspace/fake-exec"
service_path="$fake_exec_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
api_clone="$home_dir/.polyscope/clones/api12345/auto-hawk"
frontend_clone="$home_dir/.polyscope/clones/fe123456/auto-hawk"
mkdir -p "$fake_exec_dir" "$api_clone/.git/info" "$api_clone/.git/hooks" "$api_clone/scripts" "$frontend_clone/.git/info" "$frontend_clone/.git/hooks" "$frontend_clone/scripts"
mkdir -p "$home_dir/.local/bin"

python3 - <<'PY' "$fake_pg_state"
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({"databases": ["secpal"], "schemas": [], "rolcreatedb": True}))
PY

cat >"$fake_exec_dir/composer" <<'STUB'
#!/usr/bin/env bash
printf 'composer:%s:%s\n' "$PWD" "$*" >> "$PROVISION_LOG"
mkdir -p vendor
STUB
chmod +x "$fake_exec_dir/composer"

cat >"$fake_exec_dir/php" <<'STUB'
#!/usr/bin/env bash
printf 'php:%s:%s\n' "$PWD" "$*" >> "$PROVISION_LOG"
exit 0
STUB
chmod +x "$fake_exec_dir/php"

cat >"$fake_exec_dir/npm" <<'STUB'
#!/usr/bin/env bash
printf 'npm:%s:%s\n' "$PWD" "$*" >> "$PROVISION_LOG"
if [[ "$*" == *" ci"* || "$1" == "ci" ]]; then
    mkdir -p node_modules
fi
if [[ "$*" == *"run build"* ]]; then
    mkdir -p dist
    printf '<!doctype html>\n' > dist/index.html
fi
exit 0
STUB
chmod +x "$fake_exec_dir/npm"

cat >"$fake_exec_dir/psql" <<'STUB'
#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

log_path = Path(os.environ["FAKE_PSQL_LOG"])
state_path = Path(os.environ["FAKE_PSQL_STATE"])

state = {"databases": [], "schemas": [], "rolcreatedb": True}
if state_path.exists():
    state = json.loads(state_path.read_text())

args = sys.argv[1:]
sql = ""
if "-Atqc" in args:
    sql = args[args.index("-Atqc") + 1]
elif "-c" in args:
    sql = args[args.index("-c") + 1]

with log_path.open("a") as handle:
    handle.write(f"psql:{os.getcwd()}:{sql}\n")

databases = state.get("databases", [])
schemas = state.get("schemas", [])
role_match = re.search(r"SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user", sql)
exists_match = re.search(r"SELECT 1 FROM pg_database WHERE datname = '([^']+)'", sql)
list_match = re.search(r"SELECT datname FROM pg_database WHERE datname LIKE '([^']+)'", sql)
create_match = re.search(r'CREATE DATABASE "([^"]+)"', sql)
drop_match = re.search(r'DROP DATABASE IF EXISTS "([^"]+)"(?: WITH \(FORCE\))?', sql)
schema_list_match = re.search(r"SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE '([^']+)'", sql)
create_schema_match = re.search(r'CREATE SCHEMA IF NOT EXISTS "([^"]+)"', sql)
drop_schema_match = re.search(r'DROP SCHEMA IF EXISTS "([^"]+)" CASCADE', sql)

if role_match:
    sys.stdout.write("t\n" if state.get("rolcreatedb", False) else "f\n")
elif exists_match:
    database_name = exists_match.group(1)
    if database_name in databases:
        sys.stdout.write("1\n")
elif list_match:
    prefix = list_match.group(1).replace("%", "")
    matches = sorted(database_name for database_name in databases if database_name.startswith(prefix))
    if matches:
        sys.stdout.write("\n".join(matches) + "\n")
elif schema_list_match:
    prefix = schema_list_match.group(1).replace("%", "")
    matches = sorted(schema_name for schema_name in schemas if schema_name.startswith(prefix))
    if matches:
        sys.stdout.write("\n".join(matches) + "\n")
elif create_match:
    database_name = create_match.group(1)
    if database_name not in databases:
        databases.append(database_name)
elif drop_match:
    database_name = drop_match.group(1)
    databases = [entry for entry in databases if entry != database_name]
elif create_schema_match:
    schema_name = create_schema_match.group(1)
    if schema_name not in schemas:
        schemas.append(schema_name)
elif drop_schema_match:
    schema_name = drop_schema_match.group(1)
    schemas = [entry for entry in schemas if entry != schema_name]

state["databases"] = sorted(databases)
state["schemas"] = sorted(schemas)
state_path.write_text(json.dumps(state))
STUB
chmod +x "$fake_exec_dir/psql"

cat >"$home_dir/.local/bin/pre-commit" <<'STUB'
#!/usr/bin/env bash
printf 'pre-commit:%s:%s\n' "$PWD" "$*" >> "$PROVISION_LOG"
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
exit 0
HOOK
chmod +x .git/hooks/pre-commit
exit 0
STUB
chmod +x "$home_dir/.local/bin/pre-commit"

cat >"$workspace_root/api/.env" <<'EOF'
APP_URL=https://api.secpal.dev
FRONTEND_URL=https://app.secpal.dev
DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=secpal
DB_USERNAME=secpal
DB_PASSWORD=
SESSION_DOMAIN=.secpal.dev
SANCTUM_STATEFUL_DOMAINS=app.secpal.dev
CORS_ALLOWED_ORIGINS=https://app.secpal.dev
EOF

cp "$workspace_root/api/.env" "$api_clone/.env"

cat >"$api_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$api_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$api_clone/scripts/preflight.sh"

cat >"$frontend_clone/.env.local" <<'EOF'
VITE_API_URL=https://api.secpal.dev
EOF

cat >"$frontend_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$frontend_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$frontend_clone/scripts/preflight.sh"

provision_summary_json="$workspace/provision-summary.json"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$provision_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$provision_summary_json" <<'PY'
import json, sys
summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
cleaned = summary.get('cleaned_preview_storage_targets', [])
assert 'api:auto-hawk' in provisioned, f"expected api:auto-hawk in provisioned_worktrees, got {provisioned}"
assert 'frontend:auto-hawk' in provisioned, f"expected frontend:auto-hawk in provisioned_worktrees, got {provisioned}"
assert cleaned == [], f"expected no cleaned preview databases on first provisioning run, got {cleaned}"
PY

grep -qF 'APP_URL=https://api-auto-hawk.preview.secpal.dev' "$api_clone/.env"
grep -qF 'FRONTEND_URL=https://frontend-auto-hawk.preview.secpal.dev' "$api_clone/.env"
grep -qF 'DB_CONNECTION=pgsql' "$api_clone/.env"
grep -qF 'DB_DATABASE=secpal__preview__auto_hawk' "$api_clone/.env"
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$api_clone/.env"
grep -qF 'SANCTUM_STATEFUL_DOMAINS=frontend-auto-hawk.preview.secpal.dev,auto-hawk.preview.secpal.dev,app.secpal.dev' "$api_clone/.env"
grep -qF 'CORS_ALLOWED_ORIGINS=https://frontend-auto-hawk.preview.secpal.dev,https://auto-hawk.preview.secpal.dev,https://app.secpal.dev' "$api_clone/.env"
grep -qF 'VITE_API_URL=https://api-auto-hawk.preview.secpal.dev' "$frontend_clone/.env.local"
cmp -s "$workspace_root/api/polyscope.local.json" "$api_clone/polyscope.local.json"
cmp -s "$workspace_root/frontend/polyscope.local.json" "$frontend_clone/polyscope.local.json"
grep -q '^polyscope.local.json$' "$api_clone/.git/info/exclude"
grep -qF '.polyscope-secpal-provisioned.json' "$api_clone/.git/info/exclude"
test -x "$api_clone/.git/hooks/pre-commit"
test -L "$api_clone/.git/hooks/pre-push"
test "$(readlink "$api_clone/.git/hooks/pre-push")" = '../../scripts/preflight.sh'
test -x "$frontend_clone/.git/hooks/pre-commit"
test -L "$frontend_clone/.git/hooks/pre-push"
test "$(readlink "$frontend_clone/.git/hooks/pre-push")" = '../../scripts/preflight.sh'
test -f "$api_clone/.polyscope-secpal-provisioned.json"
test -f "$frontend_clone/.polyscope-secpal-provisioned.json"
grep -qF "composer:$api_clone:install" "$provision_log"
grep -qF "php:$api_clone:artisan config:clear" "$provision_log"
grep -qF "php:$api_clone:artisan migrate --force" "$provision_log"
grep -qF "php:$api_clone:artisan db:seed --force" "$provision_log"
grep -qF "php:$api_clone:artisan tinker --execute=" "$provision_log"
grep -qF "npm:$frontend_clone:ci" "$provision_log"
grep -qF "npm:$frontend_clone:run build -- --mode preview" "$provision_log"
grep -qF "pre-commit:$api_clone:install --install-hooks --hook-type pre-commit" "$provision_log"
grep -qF "pre-commit:$frontend_clone:install --install-hooks --hook-type pre-commit" "$provision_log"
grep -qF "SELECT 1 FROM pg_database WHERE datname = 'secpal__preview__auto_hawk'" "$fake_psql_log"
grep -qF 'CREATE DATABASE "secpal__preview__auto_hawk"' "$fake_psql_log"

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert 'secpal' in state['databases']
assert 'secpal__preview__auto_hawk' in state['databases']
PY

stale_api_clone="$home_dir/.polyscope/clones/api12345/stale-otter"
mkdir -p "$stale_api_clone/.git/info" "$stale_api_clone/.git/hooks" "$stale_api_clone/scripts"

cat >"$stale_api_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$stale_api_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$stale_api_clone/scripts/preflight.sh"

stale_provision_summary_json="$workspace/stale-provision-summary.json"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$stale_provision_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$stale_provision_summary_json" <<'PY'
import json, sys
summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
cleaned = summary.get('cleaned_preview_storage_targets', [])
assert 'api:stale-otter' in provisioned, f"expected api:stale-otter in provisioned_worktrees, got {provisioned}"
assert cleaned == [], f"expected no cleaned preview databases while stale-otter still exists, got {cleaned}"
PY

grep -qF 'APP_URL=https://api-stale-otter.preview.secpal.dev' "$stale_api_clone/.env"
grep -qF 'FRONTEND_URL=https://frontend-stale-otter.preview.secpal.dev' "$stale_api_clone/.env"
grep -qF 'DB_DATABASE=secpal__preview__stale_otter' "$stale_api_clone/.env"
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$stale_api_clone/.env"
test -f "$stale_api_clone/.polyscope-secpal-provisioned.json"
grep -qF 'CREATE DATABASE "secpal__preview__stale_otter"' "$fake_psql_log"

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert 'secpal__preview__stale_otter' in state['databases']
PY

rm -rf "$stale_api_clone"

# Inject a stale schema alongside the stale database to verify that in database mode
# (rolcreatedb=true) the cleanup also prunes orphaned schemas from a previous schema-mode run.
python3 - "$fake_pg_state" <<'PY'
import json, sys
state = json.loads(open(sys.argv[1]).read())
state.setdefault("schemas", []).append("secpal__preview__legacy_schema_otter")
open(sys.argv[1], "w").write(json.dumps(state))
PY

cleanup_summary_json="$workspace/cleanup-summary.json"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$cleanup_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$cleanup_summary_json" "$fake_pg_state" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
state = json.loads(open(sys.argv[2]).read())

assert summary.get('provisioned_worktrees', []) == [], summary.get('provisioned_worktrees', [])
cleaned = summary.get('cleaned_preview_storage_targets', [])
assert 'secpal__preview__stale_otter' in cleaned, f"expected stale db in cleaned, got {cleaned}"
assert 'secpal__preview__legacy_schema_otter' in cleaned, f"expected stale schema in cleaned even in database mode, got {cleaned}"
assert 'secpal__preview__auto_hawk' in state['databases']
assert 'secpal__preview__stale_otter' not in state['databases']
assert 'secpal__preview__legacy_schema_otter' not in state.get('schemas', [])
PY

grep -qF 'SELECT datname FROM pg_database WHERE datname LIKE '"'"'secpal__preview__%'"'" "$fake_psql_log"
grep -qF 'DROP DATABASE IF EXISTS "secpal__preview__stale_otter" WITH (FORCE)' "$fake_psql_log"

provision_log_lines_before="$(wc -l < "$provision_log")"
idempotent_summary_json="$workspace/idempotent-summary.json"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$idempotent_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

test "$provision_log_lines_before" -eq "$(wc -l < "$provision_log")"

python3 - "$idempotent_summary_json" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
assert summary.get('provisioned_worktrees', []) == [], summary.get('provisioned_worktrees', [])
assert summary.get('cleaned_preview_storage_targets', []) == [], summary.get('cleaned_preview_storage_targets', [])
PY

schema_home_dir="$workspace/schema-home"
schema_api_clone="$schema_home_dir/.polyscope/clones/api12345/schema-badger"
schema_frontend_clone="$schema_home_dir/.polyscope/clones/fe123456/schema-badger"
schema_pg_state="$workspace/postgres-schema-state.json"
schema_summary_json="$workspace/schema-summary.json"
schema_cleanup_summary_json="$workspace/schema-cleanup-summary.json"

mkdir -p "$schema_home_dir/.local/bin" "$schema_api_clone/.git/info" "$schema_api_clone/.git/hooks" "$schema_api_clone/scripts" "$schema_frontend_clone/.git/info" "$schema_frontend_clone/.git/hooks" "$schema_frontend_clone/scripts"
cp "$home_dir/.local/bin/pre-commit" "$schema_home_dir/.local/bin/pre-commit"

python3 - <<'PY' "$schema_pg_state"
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({"databases": ["secpal"], "schemas": [], "rolcreatedb": False}))
PY

cp "$workspace_root/api/.env" "$schema_api_clone/.env"

cat >"$schema_api_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$schema_api_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$schema_api_clone/scripts/preflight.sh"

cat >"$schema_frontend_clone/.env.local" <<'EOF'
VITE_API_URL=https://api.secpal.dev
EOF

cat >"$schema_frontend_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$schema_frontend_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$schema_frontend_clone/scripts/preflight.sh"

env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$schema_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$schema_summary_json" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
cleaned = summary.get('cleaned_preview_storage_targets', [])
assert 'api:schema-badger' in provisioned, provisioned
assert 'frontend:schema-badger' in provisioned, provisioned
assert cleaned == [], cleaned
PY

grep -qF 'DB_DATABASE=secpal' "$schema_api_clone/.env"
grep -qF 'DB_URL=postgresql://secpal@127.0.0.1:5432/secpal?search_path=secpal__preview__schema_badger' "$schema_api_clone/.env"
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$schema_api_clone/.env"
grep -qF 'POLYSCOPE_PREVIEW_STORAGE_MODE=schema' "$schema_api_clone/.env"
grep -qF 'POLYSCOPE_PREVIEW_SCHEMA=secpal__preview__schema_badger' "$schema_api_clone/.env"
grep -qF 'VITE_API_URL=https://api-schema-badger.preview.secpal.dev' "$schema_frontend_clone/.env.local"
grep -qF 'SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user' "$fake_psql_log"
grep -qF 'CREATE SCHEMA IF NOT EXISTS "secpal__preview__schema_badger"' "$fake_psql_log"

python3 - <<'PY' "$schema_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert state['databases'] == ['secpal'], state['databases']
assert 'secpal__preview__schema_badger' in state['schemas'], state['schemas']
PY

rm -rf "$schema_api_clone" "$schema_frontend_clone"

env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$schema_cleanup_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$schema_cleanup_summary_json" "$schema_pg_state" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
state = json.loads(open(sys.argv[2]).read())

assert summary.get('provisioned_worktrees', []) == [], summary.get('provisioned_worktrees', [])
assert summary.get('cleaned_preview_storage_targets', []) == ['secpal__preview__schema_badger'], summary.get('cleaned_preview_storage_targets', [])
assert 'secpal__preview__schema_badger' not in state['schemas'], state['schemas']
PY

grep -qF 'SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE '"'"'secpal__preview__%'"'" "$fake_psql_log"
grep -qF 'DROP SCHEMA IF EXISTS "secpal__preview__schema_badger" CASCADE' "$fake_psql_log"

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
fake_sudo_dir="$workspace/fake-sudo"
fake_server_bin="$workspace/fake-tools/polyscope-server"
fake_expose_real_log="$workspace/expose-real.log"
fake_git_real_log="$workspace/git-real.log"
fake_polyscope_bin_dir="$home_dir/.polyscope/bin"
fake_polyscope_git_dir="$home_dir/.local/lib/polyscope/bin"
mkdir -p "$fake_bin_dir" "$fake_unit_dir" "$fake_systemctl_dir" "$fake_sudo_dir" "$fake_polyscope_bin_dir" "$fake_polyscope_git_dir"
mkdir -p "$(dirname "$fake_server_bin")"

cat >"$fake_server_bin" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$fake_server_bin"

cat >"$fake_polyscope_bin_dir/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_EXPOSE_REAL_LOG"
exit 0
STUB
chmod +x "$fake_polyscope_bin_dir/expose-linux-x64"

cat >"$fake_systemctl_dir/systemctl" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
user_scope=0
if [[ "${1:-}" == "--user" ]]; then
    user_scope=1
    shift
fi

if [[ "${1:-}" == "show" && "${2:-}" == "-p" && "${3:-}" == "FragmentPath" && "${4:-}" == "--value" && "${5:-}" == "polyscope-server.service" ]]; then
    if [[ "$user_scope" -eq 1 ]]; then
        printf '%s\n' "${FAKE_USER_POLYSCOPE_SERVER_FRAGMENT:-}"
    else
        printf '%s\n' "${FAKE_SYSTEM_POLYSCOPE_SERVER_FRAGMENT:-}"
    fi
fi
exit 0
STUB
chmod +x "$fake_systemctl_dir/systemctl"

cat >"$fake_sudo_dir/sudo" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SUDO_LOG"

if [[ "${1:-}" == "-n" ]]; then
    shift
fi

if [[ "${1:-}" == "true" ]]; then
    exit 0
fi

exec "$@"
STUB
chmod +x "$fake_sudo_dir/sudo"

env HOME="$home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"

test -L "$fake_bin_dir/polyscope-secpal-rollout.py"
test -x "$fake_bin_dir/polyscope-secpal-rollout.py"
test -L "$fake_bin_dir/polyscope-expose-wrapper.sh"
test -x "$fake_bin_dir/polyscope-expose-wrapper.sh"
test -L "$fake_bin_dir/polyscope-git-wrapper.sh"
test -x "$fake_bin_dir/polyscope-git-wrapper.sh"
test -L "$fake_polyscope_git_dir/git"
test -x "$fake_polyscope_git_dir/git"
test "$(readlink "$fake_polyscope_git_dir/git")" = "$fake_bin_dir/polyscope-git-wrapper.sh"
test -L "$fake_polyscope_bin_dir/expose-linux-x64"
test -x "$fake_polyscope_bin_dir/expose-linux-x64"
test -x "$fake_polyscope_bin_dir/expose-linux-x64.real"
test "$(readlink "$fake_polyscope_bin_dir/expose-linux-x64")" = "$fake_bin_dir/polyscope-expose-wrapper.sh"

# Re-running the installer after the expose binary has been wrapped must stay idempotent.
env HOME="$home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"

# If the wrapped Expose path is replaced with the original real binary while .real already exists,
# the installer must still repair it idempotently instead of failing.
rm -f "$fake_polyscope_bin_dir/expose-linux-x64"
cp "$fake_polyscope_bin_dir/expose-linux-x64.real" "$fake_polyscope_bin_dir/expose-linux-x64"

env HOME="$home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"

test -L "$fake_polyscope_bin_dir/expose-linux-x64"
test "$(readlink "$fake_polyscope_bin_dir/expose-linux-x64")" = "$fake_bin_dir/polyscope-expose-wrapper.sh"

# installer must refuse to overwrite an existing .real binary
# Simulate: expose-linux-x64 is a regular file AND .real already holds a previous real binary
fake_guard_dir="$workspace/guard-test"
mkdir -p "$fake_guard_dir"
fake_guard_expose_bin="$fake_guard_dir/expose-linux-x64"
fake_guard_expose_real="$fake_guard_dir/expose-linux-x64.real"
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake_guard_expose_bin"
chmod +x "$fake_guard_expose_bin"
printf '#!/usr/bin/env bash\nexit 7\n' >"$fake_guard_expose_real"
chmod +x "$fake_guard_expose_real"
install_real_guard_exit=0
env HOME="$home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    POLYSCOPE_EXPOSE_BIN="$fake_guard_expose_bin" \
    POLYSCOPE_EXPOSE_REAL_BIN="$fake_guard_expose_real" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin" 2>/dev/null \
    || install_real_guard_exit=$?
if [[ "$install_real_guard_exit" -eq 0 ]]; then
    echo "installer guard: must refuse to overwrite existing .real binary" >&2
    exit 1
fi

system_home_dir="$workspace/system-home"
system_bin_dir="$workspace/system-bin"
system_user_unit_dir="$workspace/system-user-units"
system_dropin_dir="$workspace/system-service-units/polyscope-server.service.d"
system_polyscope_bin_dir="$system_home_dir/.polyscope/bin"
system_polyscope_git_dir="$system_home_dir/.local/lib/polyscope/bin"
system_systemctl_log="$workspace/system-systemctl.log"
system_sudo_log="$workspace/system-sudo.log"
system_fragment_dir="$workspace/system-fragments"
system_fragment_path="$system_fragment_dir/polyscope-server.service"
mkdir -p "$system_bin_dir" "$system_user_unit_dir" "$system_polyscope_bin_dir" "$system_polyscope_git_dir" "$system_fragment_dir"
printf '[Unit]\nDescription=Polyscope Server\n' > "$system_fragment_path"

cat >"$system_polyscope_bin_dir/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_EXPOSE_REAL_LOG"
exit 0
STUB
chmod +x "$system_polyscope_bin_dir/expose-linux-x64"

env HOME="$system_home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$system_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$system_sudo_log" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_FRAGMENT="$system_fragment_path" \
    POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR="$system_dropin_dir" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$system_bin_dir" --unit-dir "$system_user_unit_dir" --polyscope-server-bin "$fake_server_bin"

test ! -e "$system_user_unit_dir/polyscope-server.service"
test -f "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'ExecStart=.*/polyscope-server serve --host 127.0.0.1 --port 4321' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'ExecStartPost=/usr/bin/env bash -lc ' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q "Environment=PATH=$system_polyscope_git_dir:$system_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q "Environment=SSH_AUTH_SOCK=/run/user/%U/openssh_agent" "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'After=network-online.target' "$system_user_unit_dir/polyscope-rollout-sync.service"
grep -q 'After=polyscope-rollout-sync.service' "$system_user_unit_dir/polyscope-worktree-provision.service"
grep -q '^daemon-reload$' "$system_systemctl_log"
grep -q '^enable --now polyscope-server.service$' "$system_systemctl_log"
grep -q '^restart polyscope-server.service$' "$system_systemctl_log"
grep -q '^--user disable --now polyscope-server.service$' "$system_systemctl_log"
grep -q '^--user daemon-reload$' "$system_systemctl_log"
grep -q '^--user enable --now polyscope-rollout-sync.path$' "$system_systemctl_log"
grep -q '^--user enable --now polyscope-worktree-provision.path$' "$system_systemctl_log"
grep -q '^--user start polyscope-rollout-sync.service$' "$system_systemctl_log"
grep -q '^--user start polyscope-worktree-provision.service$' "$system_systemctl_log"

grep -q 'ExecStart=.*/polyscope-server serve --host 127.0.0.1 --port 4321' "$fake_unit_dir/polyscope-server.service"
grep -q 'ExecStartPost=/usr/bin/env bash -lc ' "$fake_unit_dir/polyscope-server.service"
grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-server.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-server.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-server.service"
grep -q 'polyscope-secpal-rollout.py --workspace-root ' "$fake_unit_dir/polyscope-server.service"
grep -q 'Restart=on-failure' "$fake_unit_dir/polyscope-server.service"
grep -q 'After=polyscope-server.service' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root .* --polyscope-api-base http://127.0.0.1:4321/api' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root ' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q '/api/.github/copilot-instructions.md' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/polyscope-rollout\.py$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -q 'After=polyscope-rollout-sync.service' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root .* --polyscope-api-base http://127.0.0.1:4321/api --clone-root .* --skip-local-configs --skip-db-sync --provision-worktrees' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -qE '^PathChanged=.*/\.polyscope/polyscope\.db$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -qE '^PathChanged=.*/api/polyscope\.local\.json$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -qE '^PathChanged=.*/frontend/polyscope\.local\.json$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -q 'daemon-reload' "$fake_systemctl_log"
grep -q 'enable --now polyscope-server.service' "$fake_systemctl_log"
grep -q 'restart polyscope-server.service' "$fake_systemctl_log"
grep -q 'enable --now polyscope-rollout-sync.path' "$fake_systemctl_log"
grep -q 'enable --now polyscope-worktree-provision.path' "$fake_systemctl_log"
grep -q 'start polyscope-rollout-sync.service' "$fake_systemctl_log"
grep -q 'start polyscope-worktree-provision.service' "$fake_systemctl_log"

# installer must refuse when system scope is detected but sudo is unavailable
no_sudo_home_dir="$workspace/no-sudo-home"
no_sudo_bin_dir="$workspace/no-sudo-bin"
no_sudo_unit_dir="$workspace/no-sudo-units"
no_sudo_polyscope_bin_dir="$no_sudo_home_dir/.polyscope/bin"
no_sudo_polyscope_git_dir="$no_sudo_home_dir/.local/lib/polyscope/bin"
no_sudo_sudo_dir="$workspace/no-sudo-fake-sudo"
no_sudo_systemctl_log="$workspace/no-sudo-systemctl.log"
no_sudo_fragment_dir="$workspace/no-sudo-fragments"
no_sudo_fragment_path="$no_sudo_fragment_dir/polyscope-server.service"
mkdir -p "$no_sudo_bin_dir" "$no_sudo_unit_dir" "$no_sudo_polyscope_bin_dir" "$no_sudo_polyscope_git_dir" "$no_sudo_sudo_dir" "$no_sudo_fragment_dir"
printf '[Unit]\nDescription=Polyscope Server\n' > "$no_sudo_fragment_path"

cat >"$no_sudo_polyscope_bin_dir/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$no_sudo_polyscope_bin_dir/expose-linux-x64"

cat >"$no_sudo_sudo_dir/sudo" <<'STUB'
#!/usr/bin/env bash
# Simulate unavailable non-interactive sudo
if [[ "${1:-}" == "-n" ]]; then
    echo "sudo: a password is required" >&2
    exit 1
fi
exec "$@"
STUB
chmod +x "$no_sudo_sudo_dir/sudo"

no_sudo_exit=0
env HOME="$no_sudo_home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$no_sudo_systemctl_log" \
    SUDO_BIN="$no_sudo_sudo_dir/sudo" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_FRAGMENT="$no_sudo_fragment_path" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$no_sudo_bin_dir" --unit-dir "$no_sudo_unit_dir" --polyscope-server-bin "$fake_server_bin" 2>/dev/null || no_sudo_exit=$?
if [[ "$no_sudo_exit" -eq 0 ]]; then
    echo "installer must refuse when system scope detected but sudo is unavailable" >&2
    exit 1
fi
test ! -e "$no_sudo_unit_dir/polyscope-server.service"

# installer must also refuse when --polyscope-server-scope system is forced but no unit exists
no_unit_exit=0
env HOME="$no_sudo_home_dir" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$no_sudo_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$no_sudo_bin_dir" --unit-dir "$no_sudo_unit_dir" --polyscope-server-bin "$fake_server_bin" --polyscope-server-scope system 2>/dev/null || no_unit_exit=$?
if [[ "$no_unit_exit" -eq 0 ]]; then
    echo "installer must refuse when --polyscope-server-scope system but no system unit exists" >&2
    exit 1
fi
test ! -e "$no_sudo_unit_dir/polyscope-server.service"

fake_real_git_bin="$workspace/fake-tools/git-real"
cat >"$fake_real_git_bin" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_GIT_REAL_LOG"
exit 0
STUB
chmod +x "$fake_real_git_bin"

env FAKE_GIT_REAL_LOG="$fake_git_real_log" \
    POLYSCOPE_REAL_GIT_BIN="$fake_real_git_bin" \
    "$fake_polyscope_git_dir/git" -C /tmp/example commit -m preview-fix >/dev/null

grep -q '^-C /tmp/example commit -S -m preview-fix$' "$fake_git_real_log"

env FAKE_GIT_REAL_LOG="$fake_git_real_log" \
    POLYSCOPE_REAL_GIT_BIN="$fake_real_git_bin" \
    "$fake_polyscope_git_dir/git" -C /tmp/example commit -S -m already-signed >/dev/null

grep -q '^-C /tmp/example commit -S -m already-signed$' "$fake_git_real_log"

# --no-gpg-sign must be rejected by the git wrapper
no_gpg_sign_exit=0
env POLYSCOPE_REAL_GIT_BIN="$fake_real_git_bin" \
    "$fake_polyscope_git_dir/git" commit --no-gpg-sign -m bypass 2>/dev/null || no_gpg_sign_exit=$?
if [[ "$no_gpg_sign_exit" -eq 0 ]]; then
    echo "git wrapper must reject --no-gpg-sign for commit" >&2
    exit 1
fi

preview_wrapper_out="$workspace/expose-wrapper-preview.out"
env HOME="$home_dir" \
    POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://frontend-auto-hawk.preview.secpal.dev:443 >"$preview_wrapper_out"

grep -q 'Shared site              https://frontend-auto-hawk.preview.secpal.dev:443' "$preview_wrapper_out"
grep -q 'Public URL               https://frontend-auto-hawk.preview.secpal.dev' "$preview_wrapper_out"

if [[ -s "$fake_expose_real_log" ]]; then
    echo "preview-domain Expose wrapper must not invoke the real Expose binary" >&2
    exit 1
fi

env HOME="$home_dir" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://example.com:443 >/dev/null

grep -q 'share https://example.com:443' "$fake_expose_real_log"
