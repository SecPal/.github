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

file_sha256() {
    python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

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
    cp "$REPO_ROOT/.markdownlint.json" "$repo_dir/.markdownlint.json"
    printf '%s' "$copilot_body" > "$repo_dir/.github/copilot-instructions.md"
    printf '%s' "$focus_body" > "$repo_dir/.github/instructions/$focus_filename"
    printf '%s' "---
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


def strip_html_comment_header(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("<!--"):
        parts = stripped.split("-->\n", 1)
        if len(parts) == 2:
            return parts[1].lstrip()
    return text


def strip_top_level_heading(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            del lines[index]
        break
    return "\n".join(lines).lstrip()


for repo_dir in workspace_root.iterdir():
    if not repo_dir.is_dir():
        continue
    copilot_path = repo_dir / ".github" / "copilot-instructions.md"
    if not copilot_path.exists():
        continue
    body = strip_top_level_heading(strip_html_comment_header(copilot_path.read_text()))
    overlay_lines = []
    for overlay_path in sorted((repo_dir / ".github" / "instructions").glob("*.instructions.md")):
        if overlay_path.name == "org-shared.instructions.md":
            overlay_lines.append(f"- `.github/instructions/{overlay_path.name}`")
        else:
            overlay_lines.append(f"- `.github/instructions/{overlay_path.name}`")
    overlays = "\n".join(overlay_lines)
    agents_text = (
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License" + "-Identifier: AGPL-3.0-or-later\n"
        "-->\n\n"
        f"# {repo_dir.name} Agent Instructions\n\n"
        "This file is the authoritative, provider-neutral runtime baseline for this repository.\n"
        "Edit this file first. Keep the focused overlay files below aligned when a rule also needs path-specific or stack-specific enforcement.\n\n"
        "## Focused Overlays\n\n"
        f"{overlays}\n\n"
        "## Core Runtime Baseline\n\n"
        f"{body.lstrip()}"
    )
    (repo_dir / "AGENTS.md").write_text(agents_text.rstrip() + "\n")

(workspace_root / "api" / "composer.json").write_text("{}\n")
(workspace_root / "api" / "artisan").write_text("#!/usr/bin/env php\n")
(workspace_root / "api" / "scripts").mkdir(parents=True, exist_ok=True)
(workspace_root / "api" / "scripts" / "preflight.sh").write_text("#!/usr/bin/env bash\n")

(workspace_root / "GuardGuide" / "composer.json").write_text("{}\n")
(workspace_root / "GuardGuide" / "artisan").write_text("#!/usr/bin/env php\n")

(workspace_root / ".github" / "scripts").mkdir(parents=True, exist_ok=True)
(workspace_root / ".github" / "scripts" / "preflight.sh").write_text("#!/usr/bin/env bash\n")

package_scripts = {
    "GuardGuide": {
        "build": "tsc --noEmit && vite build",
        "dev": "vite",
        "format:check": "prettier --check '**/*.{md,yml,yaml,json}'",
        "lint:check": "eslint .",
        "typecheck": "tsc --noEmit",
        "test": "npm run build",
    },
    "frontend": {
        "build": "vite build",
        "lint": "eslint .",
        "preflight": "./scripts/preflight.sh",
        "typecheck": "tsc --noEmit",
        "test:run": "vitest run",
        "test:run:all": "vitest run --coverage",
        "test:watch": "vitest",
        "test:e2e:ci": "cross-env CI=true playwright test",
        "test:preview:pwa-headers": "node ./scripts/check-workspace-preview-pwa-headers.mjs",
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
    "guardguide.de": {
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
        "preflight": "./scripts/preflight.sh",
    },
    ".github": {
        "copilot:review:scan": "./scripts/copilot-review-tool.sh scan",
        "test": "npm run test:openapi-verified-presence",
        "test:openapi-verified-presence": "bash tests/check-openapi-verified-endpoints.sh",
    },
}

guardguide_composer = {
    "scripts": {
        "analyse": ["./vendor/bin/phpstan analyse"],
        "lint": ["./vendor/bin/pint --test"],
        "lint:check": ["./vendor/bin/pint --test"],
        "test": ["@php artisan test"],
    }
}
(workspace_root / "GuardGuide" / "composer.json").write_text(json.dumps(guardguide_composer, indent=2) + "\n")

for repo_name, scripts in package_scripts.items():
    repo_dir = workspace_root / repo_name
    (repo_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_dir / "scripts" / "preflight.sh").write_text("#!/usr/bin/env bash\n")
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

(workspace_root / "android" / "android").mkdir(parents=True, exist_ok=True)
PY
}

seed_api_worktree_files() {
    local worktree_dir="$1"

    write_valid_worktree_instructions "$worktree_dir"
    printf '{}\n' > "$worktree_dir/composer.json"
    printf '#!/usr/bin/env php\n' > "$worktree_dir/artisan"
    chmod +x "$worktree_dir/artisan"
}

seed_node_worktree_files() {
    local worktree_dir="$1"
    local package_name="$2"

    write_valid_worktree_instructions "$worktree_dir"
    printf '{\n  "name": "%s",\n  "private": true,\n  "scripts": {\n    "build": "vite build"\n  }\n}\n' "$package_name" > "$worktree_dir/package.json"
    printf '{\n  "name": "%s",\n  "lockfileVersion": 3,\n  "requires": true,\n  "packages": {}\n}\n' "$package_name" > "$worktree_dir/package-lock.json"
}

write_valid_worktree_instructions() {
    local worktree_dir="$1"

    mkdir -p "$worktree_dir/.github"
    cp "$REPO_ROOT/.markdownlint.json" "$worktree_dir/.markdownlint.json"
    cat >"$worktree_dir/AGENTS.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Test Runtime Instructions

## Scope and Safety

- Preserve existing work.
EOF
    cat >"$worktree_dir/.github/copilot-instructions.md" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

# Test Review Profile

- Review the complete diff.
EOF
}

assert_rollout_rejects_invalid_local_config() {
    local source_script="$1"
    local old_text="$2"
    local new_text="$3"
    local expected_error="$4"
    local script_basename
    local script_copy
    local script_root
    local db_copy="$workspace/invalid-polyscope.db"
    local nginx_copy="$workspace/invalid-preview.secpal.dev.conf"
    local summary_copy="$workspace/invalid-summary.json"
    local invalid_out
    local invalid_err

    script_basename="$(basename "$source_script" .py)"
    script_root="$workspace/${script_basename}-invalid"
    script_copy="$script_root/scripts/polyscope-rollout.py"
    invalid_out="${script_copy%.py}.stdout"
    invalid_err="${script_copy%.py}.stderr"

    mkdir -p "$script_root/scripts"
    cp "$source_script" "$script_copy"
    cp "$REPO_ROOT/scripts/validate-ai-instructions.sh" \
        "$script_root/scripts/validate-ai-instructions.sh"
    if [ ! -e "$script_root/node_modules" ]; then
        ln -s "$REPO_ROOT/node_modules" "$script_root/node_modules"
    fi

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

assert_rollout_rejects_instruction_contract() {
    local repo_name="$1"
    local relative_path="$2"
    local fixture_mode="$3"
    local expected_reason="$4"
    local instruction_path="$workspace_root/$repo_name/$relative_path"
    local saved_path="$instruction_path.required-fixture"
    local fixture_slug="${repo_name//./-}-${relative_path//\//-}-$fixture_mode"
    local failure_out="$workspace/$fixture_slug.stdout"
    local failure_err="$workspace/$fixture_slug.stderr"
    local failure_nginx="$workspace/$fixture_slug.nginx"
    local failure_summary="$workspace/$fixture_slug.summary.json"
    local db_hash_before
    local repo_state_hash_before
    local unrelated_hash_before

    mv "$instruction_path" "$saved_path"
    case "$fixture_mode" in
        missing)
            ;;
        invalid-utf8)
            printf '\377' >"$instruction_path"
            ;;
        no-heading)
            cat >"$instruction_path" <<'EOF'
<!--
SPDX-FileCopyrightText: 2026 SecPal
SPDX-License-Identifier: CC0-1.0
-->

This readable instruction file has no top-level heading.
EOF
            ;;
        markdown-invalid)
            cp "$saved_path" "$instruction_path"
            printf '\n# Duplicate Top-Level Heading\n' >>"$instruction_path"
            ;;
        missing-spdx)
            sed '/SPDX-License''-Identifier:/d' "$saved_path" >"$instruction_path"
            ;;
        invalid-spdx)
            sed 's/SPDX-License''-Identifier: AGPL-3.0-or-later/SPDX-License''-Identifier: MIT/' \
                "$saved_path" >"$instruction_path"
            ;;
        oversized)
            cp "$saved_path" "$instruction_path"
            {
                printf '\n## Oversized Fixture\n\n'
                for _ in $(seq 1 700); do
                    printf '%s\n' '- filler line that exceeds the canonical instruction discovery ceiling.'
                done
            } >>"$instruction_path"
            ;;
        malformed-frontmatter)
            sed '/^applyTo:/d' "$saved_path" >"$instruction_path"
            ;;
        *)
            echo "unsupported instruction-contract fixture mode: $fixture_mode" >&2
            exit 1
            ;;
    esac

    db_hash_before="$(file_sha256 "$db_path")"
    repo_state_hash_before="$(file_sha256 "$repos_json")"
    unrelated_hash_before="$(file_sha256 "$workspace_root/api/AGENTS.md")"

    if python3 "$PYTHON_SCRIPT" \
            --workspace-root "$workspace_root" \
            --db-path "$db_path" \
            --repo-state-file "$repos_json" \
            --nginx-output "$failure_nginx" \
            --summary-output "$failure_summary" \
            >"$failure_out" 2>"$failure_err"; then
        echo "rollout must reject $fixture_mode $relative_path in $repo_name" >&2
        exit 1
    fi

    if ! grep -qF "canonical AI-instruction validation failed for $workspace_root/$repo_name" \
        "$failure_err"; then
        sed -n '1,240p' "$failure_err" >&2
        echo "canonical validation failure did not identify $workspace_root/$repo_name" >&2
        exit 1
    fi
    grep -qF "$relative_path" "$failure_err"
    grep -qF 'canonical AI-instruction validation failed' "$failure_err"
    grep -qF "$expected_reason" "$failure_err"
    test ! -e "$failure_nginx"
    test ! -e "$failure_summary"
    test "$(file_sha256 "$db_path")" = "$db_hash_before"
    test "$(file_sha256 "$repos_json")" = "$repo_state_hash_before"
    test "$(file_sha256 "$workspace_root/api/AGENTS.md")" = "$unrelated_hash_before"
    if find "$workspace_root" -name 'polyscope.local.json' -print -quit | grep -q .; then
        echo "failed canonical validation must precede local configuration writes" >&2
        exit 1
    fi
    if find "$workspace" -name '.polyscope-secpal-provisioned.json' -print -quit | grep -q .; then
        echo "failed canonical validation must not mark a worktree provisioned" >&2
        exit 1
    fi

    if [ "$fixture_mode" = "missing" ]; then
        test ! -e "$instruction_path"
    else
        rm "$instruction_path"
    fi
    mv "$saved_path" "$instruction_path"
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

create_repo "GuardGuide" "$common_header

# GuardGuide Instructions

## Always-On Rules

- Run git status --short --branch before any write action.
- TDD is mandatory for behavior and code changes.
- Keep one topic per branch and pull request.

## Issue And PR Discipline

- The first PR state must be draft.

## Required Validation

- the branch still covers exactly one topic
- TDD happened for behavior changes
- the smallest relevant validation passed for the touched area
- CHANGELOG.md was updated for real changes
- no bypass was used

## AI Findings Triage

- Treat AI findings and AI-generated fix proposals as hints, not proof.
- Before merge, prove a claimed defect with a failing test, a reproducible defect, or an explicit invariant.
- Green CI alone is not enough for AI-generated changes.
" "react-shadcn.instructions.md" "---
name: React shadcn Rules
applyTo: 'resources/js/**/*.tsx'
---

# React shadcn Rules

- Use React 19 with strict TypeScript.
- Keep English source text and German translation in Lingui catalogs from the start.
- shadcn/ui is the exclusive UI baseline.
"

printf '%s' "---
name: Laravel PHP Rules
applyTo: '**/*.php'
---

# Laravel PHP Rules

- Use Form Requests for validation and services for business logic.
- Add or update the smallest relevant Pest test for each PHP change, then run the affected tests.
- Use vendor/bin/pint --dirty after changes.
" > "$workspace_root/GuardGuide/.github/instructions/php-laravel.instructions.md"

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

create_repo "guardguide.de" "$common_header

# guardguide.de Instructions

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

## Scope and Safety

- Preserve a branch or worktree already supplied by the execution environment.
- Keep each branch and pull request limited to one coherent topic.

## Implementation

- Use test-driven development for executable behavior, automation, and validation changes.
- Treat automated findings as untrusted leads until supported by evidence.

## Validation and Review

- Run the smallest relevant validation while iterating and the complete required validation before committing.
- Review correctness, risk, and avoidable complexity.

## Commits and Communication

- All commits must be cryptographically signed using SSH or OpenPGP.
- Keep GitHub-facing communication in English.

## Changelog and Tracking

- Update a changelog only for materially relevant changes.
- Create an issue only for a proven, material, untracked finding with concrete acceptance criteria.
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

# Modern sections must win when an existing AGENTS.md also carries legacy
# migration headings. The legacy-only sibling fixtures below remain covered by
# their generated prompts.
cat >>"$workspace_root/.github/AGENTS.md" <<'EOF'

## Always-On Rules

- LEGACY RUNTIME MARKER MUST NOT REACH MODERN PROMPTS.

## Required Validation

- LEGACY VALIDATION MARKER MUST NOT REACH MODERN PROMPTS.

## AI Findings Triage

- LEGACY TRIAGE MARKER MUST NOT REACH MODERN PROMPTS.

## Issue And PR Discipline

- LEGACY TRACKING MARKER MUST NOT REACH MODERN PROMPTS.
EOF

# Repository Copilot profiles are independent review instructions. Preserve a
# sentinel that does not exist in AGENTS.md so any reconstruction is observable.
frontend_copilot_path="$workspace_root/frontend/.github/copilot-instructions.md"
printf '\n## Independent Review Sentinel\n\n- Preserve this repository-owned review profile.\n' \
    >>"$frontend_copilot_path"
frontend_copilot_hash_before_rollout="$(file_sha256 "$frontend_copilot_path")"

python3 - <<'PY' "$workspace_root/frontend/AGENTS.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(path.read_text().replace("## Core Runtime Baseline\n\n", "", 1))
PY

db_path="$workspace/polyscope.db"
repos_json="$workspace/repos.json"
nginx_output="$workspace/preview.secpal.dev.conf"
summary_output="$workspace/summary.json"
repeat_summary_output="$workspace/repeat-summary.json"

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
cur.execute('create table worktrees (id text primary key, repo_id text not null, branch text not null, path text not null, status text default \'active\' not null, created_at text default (datetime(\'now\')) not null)')

repo_state = {
    'api': {'id': 'api12345', 'name': 'SecPal/api', 'path': str(workspace_root / 'api')},
    'frontend': {'id': 'fe123456', 'name': 'SecPal/frontend', 'path': str(workspace_root / 'frontend')},
    'contracts': {'id': 'co123456', 'name': 'SecPal/contracts', 'path': str(workspace_root / 'contracts')},
    'android': {'id': 'an123456', 'name': 'SecPal/android', 'path': str(workspace_root / 'android')},
    'secpal.app': {'id': 'sa123456', 'name': 'SecPal/secpal.app', 'path': str(workspace_root / 'secpal.app')},
    'guardguide.de': {'id': 'gd123456', 'name': 'SecPal/guardguide.de', 'path': str(workspace_root / 'guardguide.de')},
    'changelog': {'id': 'ch123456', 'name': 'SecPal/changelog', 'path': str(workspace_root / 'changelog')},
    'GuardGuide': {'id': 'gg123456', 'name': 'SecPal/GuardGuide', 'path': str(workspace_root / 'GuardGuide')},
    '.github': {'id': 'gh123456', 'name': 'SecPal/.github', 'path': str(workspace_root / '.github')},
}

for repo in repo_state.values():
    cur.execute('insert into repositories (id, name, path, created_at, base_branch, github_assign_self_enabled) values (?, ?, ?, datetime(\'now\'), ?, ?)', (repo['id'], repo['name'], repo['path'], 'main', 0))

conn.commit()
conn.close()
repos_json.write_text(json.dumps(repo_state, indent=2))
PY

replace_registered_worktrees() {
    python3 - "$db_path" "$@" <<'PY'
import sqlite3
import sys

db_path, *registrations = sys.argv[1:]
if len(registrations) % 2:
    raise SystemExit("registered-worktree fixtures require repo-id/path pairs")

with sqlite3.connect(db_path) as connection:
    connection.execute("delete from worktrees")
    for index in range(0, len(registrations), 2):
        repo_id, path = registrations[index : index + 2]
        worktree_id = f"fixture-{index // 2:04d}"
        connection.execute(
            "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
            (worktree_id, repo_id, f"branch-{index // 2:04d}", path),
        )
PY
}

assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "missing" 'Missing: AGENTS.md'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "invalid-utf8" \
    'File must be non-empty UTF-8 Markdown with a top-level heading'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "no-heading" \
    'File must be non-empty UTF-8 Markdown with a top-level heading'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "markdown-invalid" 'instruction Markdown passes lint'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "missing-spdx" 'Missing inline SPDX header or .license sidecar'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "invalid-spdx" 'Missing inline SPDX header or .license sidecar'
assert_rollout_rejects_instruction_contract \
    "GuardGuide" "AGENTS.md" "oversized" 'bytes exceeds 32768 bytes'
assert_rollout_rejects_instruction_contract \
    "frontend" ".github/copilot-instructions.md" "missing" \
    'Missing: .github/copilot-instructions.md'
assert_rollout_rejects_instruction_contract \
    "frontend" ".github/copilot-instructions.md" "markdown-invalid" \
    'instruction Markdown passes lint'
assert_rollout_rejects_instruction_contract \
    "frontend" ".github/copilot-instructions.md" "oversized" 'bytes exceeds 32768 bytes'
assert_rollout_rejects_instruction_contract \
    "frontend" ".github/instructions/org-shared.instructions.md" \
    "malformed-frontmatter" 'instruction overlays include valid frontmatter'

# All direct API-worktree CLI modes are instruction-dependent. Exercise their
# shared validation boundary through the real CLI and canonical validator before
# the normal rollout creates any local configuration or metadata.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace" "$REPO_ROOT"
import importlib.util
import itertools
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
repo_root = pathlib.Path(sys.argv[3])
fixture_root = workspace / "direct API CLI validation with spaces"
fake_bin = fixture_root / "fake bin"
side_effect_log = fixture_root / "command-side-effects.log"
fake_bin.mkdir(parents=True)

for executable in ("composer", "php", "psql"):
    executable_path = fake_bin / executable
    executable_path.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' '{executable}:$*' >>\"$SIDE_EFFECT_LOG\"\n"
        "exit 0\n"
    )
    executable_path.chmod(0o755)


def write_valid_instruction_root(root: pathlib.Path) -> None:
    (root / ".github").mkdir(parents=True)
    shutil.copy2(repo_root / ".markdownlint.json", root / ".markdownlint.json")
    (root / "AGENTS.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License" "-Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Runtime Instructions\n\n"
        "## Scope and Safety\n\n"
        "- Preserve existing work.\n"
    )
    (root / ".github" / "copilot-instructions.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License" "-Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Review Profile\n\n"
        "- Review the complete diff.\n"
    )
    (root / ".env.example").write_text(
        "APP_ENV=local\n"
        "APP_KEY=base64:test-key\n"
        "APP_URL=http://localhost\n"
        "FRONTEND_URL=http://localhost\n"
        "DB_CONNECTION=sqlite\n"
    )


def invalidate_instruction(root: pathlib.Path, instruction_kind: str) -> str:
    if instruction_kind == "agents":
        with (root / "AGENTS.md").open("a") as handle:
            handle.write("\n# Duplicate Top-Level Heading\n")
        return "instruction Markdown passes lint"

    copilot_path = root / ".github" / "copilot-instructions.md"
    copilot_path.write_text(
        copilot_path.read_text().replace(
            "SPDX-License" "-Identifier: CC0-1.0\n",
            "",
        )
    )
    return "Missing inline SPDX header or .license sidecar"


def cli_arguments(
    mode: str,
    target: pathlib.Path,
    source: pathlib.Path,
    run_marker: pathlib.Path,
    db_path: pathlib.Path,
) -> list[str]:
    arguments = [
        sys.executable,
        str(script_path),
        f"--{mode.replace('_', '-')}",
        str(target),
        "--source-repo-path",
        str(source),
        "--db-path",
        str(db_path),
    ]
    if mode == "run_api_worktree":
        arguments.extend(["--shell-command", f"touch {shlex.quote(str(run_marker))}"])
    return arguments


def cli_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
    environment["SIDE_EFFECT_LOG"] = str(side_effect_log)
    return environment


modes = (
    "prepare_api_worktree",
    "bootstrap_api_worktree",
    "refresh_api_worktree",
    "run_api_worktree",
)
failure_classes = tuple(itertools.product(("source", "target"), ("agents", "copilot")))

for mode in modes:
    for invalid_root_kind, instruction_kind in failure_classes:
        case_root = fixture_root / f"{mode}-{invalid_root_kind}-{instruction_kind}"
        source = case_root / "source repository"
        target = case_root / "target worktree"
        run_marker = case_root / "runtime-command-ran"
        unrelated = case_root / "unrelated-state"
        db_path = case_root / "polyscope.db"
        write_valid_instruction_root(source)
        write_valid_instruction_root(target)
        unrelated.write_text("unchanged\n")

        env_path = target / ".env"
        if mode == "run_api_worktree" or instruction_kind == "copilot":
            env_path.write_text(
                "APP_ENV=local\n"
                "APP_KEY=base64:existing-key\n"
                "DB_CONNECTION=sqlite\n"
            )
        env_existed = env_path.exists()
        env_before = env_path.read_bytes() if env_existed else None
        unrelated_before = unrelated.read_bytes()

        invalid_root = source if invalid_root_kind == "source" else target
        expected_reason = invalidate_instruction(invalid_root, instruction_kind)
        side_effect_log.unlink(missing_ok=True)

        result = subprocess.run(
            cli_arguments(mode, target, source, run_marker, db_path),
            env=cli_environment(),
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            f"{mode} accepted invalid {invalid_root_kind} {instruction_kind}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert str(invalid_root.resolve()) in result.stderr, result.stderr
        assert "canonical AI-instruction validation failed" in result.stderr, result.stderr
        assert expected_reason in result.stderr, result.stderr
        assert "Healed api worktree" not in result.stdout, result.stdout
        assert "[api:" not in result.stdout, result.stdout
        assert env_path.exists() is env_existed
        if env_existed:
            assert env_path.read_bytes() == env_before
        assert unrelated.read_bytes() == unrelated_before
        assert not side_effect_log.exists(), side_effect_log.read_text() if side_effect_log.exists() else ""
        assert not run_marker.exists()
        assert not db_path.exists()
        assert not (target / ".polyscope-secpal-provisioned.json").exists()

# Fully valid source and target roots must retain successful CLI behavior for
# every classified mode.
positive_source = fixture_root / "positive source repository"
write_valid_instruction_root(positive_source)
for mode in modes:
    positive_case = fixture_root / f"positive-{mode}"
    positive_target = positive_case / "target worktree"
    positive_run_marker = positive_case / "runtime-command-ran"
    positive_db_path = positive_case / "polyscope.db"
    write_valid_instruction_root(positive_target)
    if mode != "prepare_api_worktree":
        (positive_target / ".env").write_text(
            "APP_ENV=local\n"
            "APP_KEY=base64:existing-key\n"
            "DB_CONNECTION=sqlite\n"
        )
    side_effect_log.unlink(missing_ok=True)

    result = subprocess.run(
        cli_arguments(mode, positive_target, positive_source, positive_run_marker, positive_db_path),
        env=cli_environment(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"valid {mode} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if mode == "prepare_api_worktree":
        assert (positive_target / ".env").exists()
    elif mode in {"bootstrap_api_worktree", "refresh_api_worktree"}:
        assert side_effect_log.exists()
        assert "php:" in side_effect_log.read_text()
    else:
        assert positive_run_marker.exists()

# The explicit classification is shared by argument registration and dispatch;
# adding another direct instruction-dependent mode requires extending this set.
module_spec = importlib.util.spec_from_file_location("polyscope_rollout_direct_modes", script_path)
module = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(module)
assert module.INSTRUCTION_DEPENDENT_DIRECT_API_MODES == modes

# A copied real validator with no pinned node_modules and an isolated PATH must
# block a direct mode before any target mutation instead of downloading tooling.
isolated_root = fixture_root / "missing markdownlint toolchain"
isolated_script_root = isolated_root / "governance"
isolated_bin = isolated_root / "bin"
isolated_source = isolated_root / "source repository"
isolated_target = isolated_root / "target worktree"
isolated_script_root.mkdir(parents=True)
isolated_bin.mkdir()
isolated_source.mkdir()
isolated_target.mkdir()
isolated_rollout = isolated_script_root / "polyscope-rollout.py"
isolated_validator = isolated_script_root / "validate-ai-instructions.sh"
shutil.copy2(script_path, isolated_rollout)
shutil.copy2(repo_root / "scripts" / "validate-ai-instructions.sh", isolated_validator)
write_valid_instruction_root(isolated_source)
write_valid_instruction_root(isolated_target)
isolated_env_path = isolated_target / ".env"
isolated_env_path.write_text("APP_KEY=base64:unchanged\nDB_CONNECTION=sqlite\n")
isolated_env_before = isolated_env_path.read_bytes()

for required_tool in ("bash", "basename", "dirname", "find", "grep", "head", "python3", "wc"):
    tool_path = shutil.which(required_tool)
    assert tool_path is not None, required_tool
    (isolated_bin / required_tool).symlink_to(tool_path)

isolated_environment = os.environ.copy()
isolated_environment["PATH"] = str(isolated_bin)
isolated_environment["SIDE_EFFECT_LOG"] = str(side_effect_log)
side_effect_log.unlink(missing_ok=True)
isolated_result = subprocess.run(
    [
        sys.executable,
        str(isolated_rollout),
        "--prepare-api-worktree",
        str(isolated_target),
        "--source-repo-path",
        str(isolated_source),
        "--db-path",
        str(isolated_root / "polyscope.db"),
    ],
    env=isolated_environment,
    capture_output=True,
    text=True,
)
assert isolated_result.returncode != 0, isolated_result.stdout + isolated_result.stderr
assert str(isolated_source.resolve()) in isolated_result.stderr, isolated_result.stderr
assert "Markdownlint is unavailable" in isolated_result.stderr, isolated_result.stderr
assert isolated_env_path.read_bytes() == isolated_env_before
assert not side_effect_log.exists()
assert not (isolated_root / "polyscope.db").exists()
assert "All tests passed" not in isolated_result.stderr
PY

python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$summary_output" \
    > /dev/null

frontend_copilot_hash_after_rollout="$(file_sha256 "$frontend_copilot_path")"
if [ "$frontend_copilot_hash_after_rollout" != "$frontend_copilot_hash_before_rollout" ]; then
    echo "rollout must not reconstruct or overwrite an independent Copilot profile" >&2
    exit 1
fi
grep -qF '## Independent Review Sentinel' "$frontend_copilot_path"

# Provisionability requires both independent instruction files in each
# worktree, not merely the Copilot review profile.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "instruction-contract-worktree"
(fixture / ".git").mkdir(parents=True)
(fixture / ".github").mkdir()
(fixture / ".markdownlint.json").write_text('{"default": true}\n')
(fixture / "AGENTS.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Runtime Instructions\n"
)
(fixture / ".github" / "copilot-instructions.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Review Profile\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

assert module.is_provisionable_worktree(
    "frontend",
    fixture,
    [],
    validated_instruction_roots=set(),
    log_skip_reason=False,
)

valid_agents = (fixture / "AGENTS.md").read_text()
(fixture / "AGENTS.md").write_text(valid_agents + "\n# Duplicate Heading\n")
try:
    module.is_provisionable_worktree(
        "frontend",
        fixture,
        [],
        validated_instruction_roots=set(),
        log_skip_reason=False,
    )
except module.CanonicalInstructionValidationError as error:
    assert str(fixture) in str(error), error
    assert "instruction Markdown passes lint" in str(error), error
else:
    raise AssertionError("Markdown-invalid AGENTS.md must fail canonical worktree validation")
(fixture / "AGENTS.md").write_text(valid_agents)

copilot_path = fixture / ".github" / "copilot-instructions.md"
valid_copilot = copilot_path.read_text()
copilot_path.write_text(valid_copilot.replace("SPDX-License" "-Identifier: CC0-1.0\n", ""))
try:
    module.is_provisionable_worktree(
        "frontend",
        fixture,
        [],
        validated_instruction_roots=set(),
        log_skip_reason=False,
    )
except module.CanonicalInstructionValidationError as error:
    assert str(fixture) in str(error), error
    assert "Missing inline SPDX header or .license sidecar" in str(error), error
else:
    raise AssertionError("unlicensed Copilot instructions must fail canonical worktree validation")

assert not (fixture / "polyscope.local.json").exists()
assert not (fixture / ".polyscope-secpal-provisioned.json").exists()
PY

# Canonical validation uses argv-safe paths, caches each resolved root after a
# real successful run, and fails closed when its validator cannot execute.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace" "$REPO_ROOT"
import importlib.util
import pathlib
import shutil
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
repo_root = pathlib.Path(sys.argv[3])

spec = importlib.util.spec_from_file_location("polyscope_rollout_validator", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

fixture = workspace / "instruction root with shell $ characters"
(fixture / ".github").mkdir(parents=True)
(fixture / ".markdownlint.json").write_text((repo_root / ".markdownlint.json").read_text())
(fixture / "AGENTS.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Runtime Instructions\n"
)
(fixture / ".github" / "copilot-instructions.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Review Profile\n"
)

validated_roots: set[pathlib.Path] = set()
resolved_fixture = module.validate_instruction_root(fixture, validated_roots)
assert resolved_fixture == fixture.resolve()
assert validated_roots == {fixture.resolve()}

original_validator = module.CANONICAL_AI_INSTRUCTIONS_VALIDATOR
missing_validator = workspace / "missing-validate-ai-instructions.sh"
module.CANONICAL_AI_INSTRUCTIONS_VALIDATOR = missing_validator
assert module.validate_instruction_root(fixture, validated_roots) == fixture.resolve()

uncached_fixture = workspace / "uncached instruction root"
shutil.copytree(fixture, uncached_fixture)
try:
    module.validate_instruction_root(uncached_fixture, validated_roots)
except module.CanonicalInstructionValidationError as error:
    assert str(uncached_fixture) in str(error), error
    assert str(missing_validator) in str(error), error
    assert "missing or not executable" in str(error), error
else:
    raise AssertionError("a missing canonical validator must block an uncached root")

nonexecutable_validator = workspace / "nonexecutable-validate-ai-instructions.sh"
nonexecutable_validator.write_text("#!/usr/bin/env bash\nexit 0\n")
module.CANONICAL_AI_INSTRUCTIONS_VALIDATOR = nonexecutable_validator
try:
    module.validate_instruction_root(uncached_fixture, validated_roots)
except module.CanonicalInstructionValidationError as error:
    assert "missing or not executable" in str(error), error
else:
    raise AssertionError("a non-executable canonical validator must block validation")

module.CANONICAL_AI_INSTRUCTIONS_VALIDATOR = original_validator
PY

assert_rollout_rejects_invalid_local_config \
    "$PYTHON_SCRIPT" \
    'composer run analyse' \
    'composer run missing-script' \
    "GuardGuide polyscope config references missing composer script 'missing-script'"

grep -q 'https://api-{{worktree}}.preview.secpal.dev' "$workspace_root/api/polyscope.local.json"
grep -q 'Apply the current SecPal instructions from ' "$workspace_root/api/polyscope.local.json"
grep -q 'AGENTS.md' "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --prepare-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api" "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --bootstrap-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api" "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --run-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api --shell-command 'php artisan queue:work --queue=activity-hash-chain,merkle,opentimestamp,default --sleep=3 --tries=3'" "$workspace_root/api/polyscope.local.json"
grep -qF '"label": "Scheduler"' "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --run-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api --shell-command 'php artisan schedule:work'" "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --run-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api --shell-command 'php artisan pail --timeout=0'" "$workspace_root/api/polyscope.local.json"
grep -A3 '"label": "Scheduler"' "$workspace_root/api/polyscope.local.json" | grep -qF '"autostart": true'
if grep -qF 'php artisan queue:listen --tries=1' "$workspace_root/api/polyscope.local.json"; then
    echo "preview API queue worker must use combined queue:work and not queue:listen" >&2
    exit 1
fi
if grep -qF '"command": "php artisan schedule:work"' "$workspace_root/api/polyscope.local.json"; then
    echo "preview API scheduler must run through the rollout runtime env wrapper" >&2
    exit 1
fi
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace_root"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace_root = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

api_run_actions = module.REPO_SETTINGS["api"]["local_config"]["scripts"]["run"]
queue_worker_action = next(
    (action for action in api_run_actions if action["label"] == "Queue Worker"),
    None,
)
assert queue_worker_action is not None, api_run_actions
assert queue_worker_action.get("autostart") is True, queue_worker_action
assert "--max-time" not in queue_worker_action["command"], queue_worker_action
api_run_actions[0]["label"] = "Background Queue"
api_run_actions[1]["label"] = "Cron Loop"
api_run_actions[2]["label"] = "Log Tail"
api_spec = module.build_repo_specs(workspace_root)["api"]
runtime_commands = [
    action["command"]
    for action in api_spec["local_config"]["scripts"]["run"][:3]
]
assert all("--run-api-worktree" in command for command in runtime_commands), runtime_commands
PY
grep -qF 'Preview Only: Refresh DB + E2E User' "$workspace_root/api/polyscope.local.json"
grep -qF "python3 $PYTHON_SCRIPT --refresh-api-worktree \\\"\$PWD\\\" --source-repo-path $workspace_root/api" "$workspace_root/api/polyscope.local.json"
grep -qF '"label": "All Checks"' "$workspace_root/api/polyscope.local.json"
grep -qF '"command": "php artisan test && vendor/bin/pint --dirty && vendor/bin/phpstan analyse --no-progress"' "$workspace_root/api/polyscope.local.json"
grep -qF '"label": "Preflight"' "$workspace_root/api/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/api/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/api/polyscope.local.json"
grep -qF '"copyGitignored": false' "$workspace_root/api/polyscope.local.json"
if grep -qF '"command": "php artisan migrate:fresh --seed"' "$workspace_root/api/polyscope.local.json"; then
    echo "preview API refresh command must use the hardened reseed flow and not raw migrate:fresh --seed" >&2
    exit 1
fi
grep -q 'frontend/AGENTS.md before taking action' "$workspace_root/frontend/polyscope.local.json"
grep -q 'https://frontend-{{worktree}}.preview.secpal.dev' "$workspace_root/frontend/polyscope.local.json"
grep -qF '# Org Instructions' "$workspace_root/.github/.github/copilot-instructions.md"
# shellcheck disable=SC2016 # Backticks are literal Markdown in the expected text.
if grep -qF 'mirrors the authoritative root `AGENTS.md`' \
    "$workspace_root/.github/.github/copilot-instructions.md"; then
    echo "rollout must not introduce the obsolete Copilot mirror declaration" >&2
    exit 1
fi
grep -q '## Always-On Rules' "$workspace_root/frontend/.github/copilot-instructions.md"
grep -q 'https://guardguide-{{worktree}}.preview.secpal.dev' "$workspace_root/GuardGuide/polyscope.local.json"
grep -q 'https://secpal-app-{{worktree}}.preview.secpal.dev' "$workspace_root/secpal.app/polyscope.local.json"
grep -q 'https://guardguide-de-{{worktree}}.preview.secpal.dev' "$workspace_root/guardguide.de/polyscope.local.json"
grep -q 'https://changelog-{{worktree}}.preview.secpal.dev' "$workspace_root/changelog/polyscope.local.json"
grep -qF '.env.local' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'VITE_API_URL' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'resolve_linked_workspace(\"SecPal/api\", workspace)' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'Watching frontend preview sources for changes...' "$workspace_root/frontend/polyscope.local.json"
grep -qF '"command": "npm run lint && npm run typecheck && npm run test:run:all && npm run build"' "$workspace_root/frontend/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/frontend/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/frontend/polyscope.local.json"
grep -qF '"label": "Workspace Preview CSP Smoke"' "$workspace_root/frontend/polyscope.local.json"
grep -qF '"command": "npm run test:preview:pwa-headers"' "$workspace_root/frontend/polyscope.local.json"
if grep -qF "npx vite build --watch --mode preview" "$workspace_root/frontend/polyscope.local.json"; then
    echo "generated frontend Polyscope config must not rely on Vite watch mode for preview rebuilds" >&2
    exit 1
fi
grep -q 'npm run test:e2e:ci' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'PLAYWRIGHT_BASE_URL' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'PLAYWRIGHT_API_BASE_URL' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'POLYSCOPE_WORKSPACE' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'tests/e2e/smoke.spec.ts' "$workspace_root/frontend/polyscope.local.json"
grep -qF -- '--project=chromium' "$workspace_root/frontend/polyscope.local.json"
grep -qF -- '--project=mobile-chrome' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'TEST_USER_EMAIL' "$workspace_root/frontend/polyscope.local.json"
if grep -q 'test:e2e:staging' "$workspace_root/frontend/polyscope.local.json"; then
    echo "generated frontend Polyscope config must not reference the removed test:e2e:staging script" >&2
    exit 1
fi
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

python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace" "$REPO_ROOT"
import importlib.util
import os
import pathlib
import shutil
import shlex
import sqlite3
import subprocess
import sys
import time

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
repo_root = pathlib.Path(sys.argv[3])
fixture = workspace / "linked-preview-fixture"
db_path = fixture / "polyscope.db"
frontend_worktree = fixture / "clones" / "fe123456" / "azure-cheetah"
api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-165552b7"
relinked_api_worktree = fixture / "clones" / "api12345" / "crimson-link"
source_api = fixture / "source-api"
frontend_worktree.mkdir(parents=True)
api_worktree.mkdir(parents=True)
relinked_api_worktree.mkdir(parents=True)
source_api.mkdir(parents=True)
fake_bin = fixture / "fake-bin"
fake_bin.mkdir()

for instruction_root in (source_api, api_worktree):
    instruction_root.joinpath(".github").mkdir(exist_ok=True)
    shutil.copy2(repo_root / ".markdownlint.json", instruction_root / ".markdownlint.json")
    instruction_root.joinpath("AGENTS.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License" "-Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Runtime Instructions\n\n"
        "- Preserve existing work.\n"
    )
    instruction_root.joinpath(".github", "copilot-instructions.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License" "-Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Review Profile\n\n"
        "- Review the complete diff.\n"
    )

source_api.joinpath(".env").write_text(
    "\n".join(
        [
            "APP_URL=https://api.secpal.dev",
            "FRONTEND_URL=https://app.secpal.dev",
            "DB_CONNECTION=sqlite",
            "SESSION_DOMAIN=.secpal.dev",
            "SANCTUM_STATEFUL_DOMAINS=app.secpal.dev",
            "CORS_ALLOWED_ORIGINS=https://app.secpal.dev",
            "",
        ]
    )
)
api_worktree.joinpath(".env").write_text(source_api.joinpath(".env").read_text())
frontend_worktree.joinpath(".env.local").write_text("VITE_API_URL=https://api.secpal.dev\n")

with sqlite3.connect(db_path) as connection:
    connection.executescript(
        """
        create table repositories (id text primary key, name text not null, path text not null);
        create table worktrees (id text primary key, repo_id text not null, branch text not null, path text not null, created_at text default (datetime('now')) not null);
        create table worktree_links (worktree_id text not null, linked_worktree_id text not null, created_at text default (datetime('now')) not null);
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [
            ("api12345", "SecPal/api", str(source_api)),
            ("fe123456", "SecPal/frontend", str(fixture / "source-frontend")),
        ],
    )
    connection.executemany(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        [
            ("api-worktree", "api12345", "not-the-workspace", str(api_worktree)),
            ("api-worktree-relinked", "api12345", "crimson-link", str(relinked_api_worktree)),
            ("frontend-worktree", "fe123456", "not-the-workspace", str(frontend_worktree)),
        ],
    )
    connection.executemany(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        [
            ("frontend-worktree", "api-worktree"),
            ("api-worktree", "frontend-worktree"),
        ],
    )

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

module.ensure_workspace_alias(api_worktree, db_path=db_path)

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(db_path)
subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_frontend_preview_env_setup_command()],
    cwd=frontend_worktree,
    env=env,
    check=True,
)
frontend_env = frontend_worktree.joinpath(".env.local").read_text()
assert "VITE_API_URL=https://api-azure-cheetah.preview.secpal.dev" in frontend_env, frontend_env
assert "not-the-workspace" not in frontend_env, frontend_env

ready, _ = module.ensure_api_worktree_ready(api_worktree, source_api, db_path=db_path)
assert ready
api_env = api_worktree.joinpath(".env").read_text()
assert "APP_URL=https://api-azure-cheetah.preview.secpal.dev" in api_env, api_env
assert "FRONTEND_URL=https://frontend-azure-cheetah.preview.secpal.dev" in api_env, api_env
assert "SANCTUM_STATEFUL_DOMAINS=frontend-azure-cheetah.preview.secpal.dev,azure-cheetah.preview.secpal.dev,app.secpal.dev" in api_env, api_env
assert "CORS_ALLOWED_ORIGINS=https://frontend-azure-cheetah.preview.secpal.dev,https://azure-cheetah.preview.secpal.dev,https://app.secpal.dev" in api_env, api_env

setup_commands = [module.build_frontend_preview_env_setup_command(), "npm run build -- --mode preview"]
initial_setup_hash = module.build_setup_hash(frontend_worktree, setup_commands, db_path=db_path)
with sqlite3.connect(db_path) as connection:
    connection.execute(
        "delete from worktree_links where worktree_id = ? and linked_worktree_id = ?",
        ("frontend-worktree", "api-worktree"),
    )
    connection.execute(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        ("frontend-worktree", "api-worktree-relinked"),
    )
changed_setup_hash = module.build_setup_hash(frontend_worktree, setup_commands, db_path=db_path)
assert changed_setup_hash != initial_setup_hash, "linked workspace changes must invalidate frontend provisioning"
with sqlite3.connect(db_path) as connection:
    connection.execute(
        "delete from worktree_links where worktree_id = ? and linked_worktree_id = ?",
        ("frontend-worktree", "api-worktree-relinked"),
    )
    connection.execute(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        ("frontend-worktree", "api-worktree"),
    )

# build_frontend_preview_build_command: assert linked API workspace is used in VITE_API_URL
fake_npm = fake_bin / "npm"
fake_npm.write_text(
    """#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
out_dir = Path("dist")
for index, arg in enumerate(args[:-1]):
    if arg == "--outDir":
        out_dir = Path(args[index + 1])
        break

Path("npm-vite-api-url.log").write_text(os.environ.get("VITE_API_URL", "") + "\\n")

if "run" in args and "build" in args:
    active_build_path = Path(".fake-npm-build-active")
    try:
        active_build_fd = os.open(active_build_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        Path(".fake-npm-build-overlap").write_text("overlap\\n")
        sys.exit(99)
    os.close(active_build_fd)
    if os.environ.get("FAKE_NPM_BUILD_DELAY"):
        time.sleep(float(os.environ["FAKE_NPM_BUILD_DELAY"]))
    active_build_path.unlink()

    counter_path = Path(".fake-npm-build-count")
    counter = int(counter_path.read_text()) if counter_path.exists() else 0
    counter_path.write_text(str(counter + 1))

    if os.environ.get("FAKE_NPM_FAIL_ALWAYS_BUILD_127") == "1" or (
        os.environ.get("FAKE_NPM_FAIL_WITHOUT_BUILD_BINARIES") == "1"
        and not all(
            Path(f"node_modules/.bin/{binary}").exists()
            for binary in ("cross-env", "vite")
        )
    ):
        sys.exit(127)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(f"<!doctype html>build {counter}\\n")
    if os.environ.get("FAKE_NPM_SYMLINK") == "1":
        Path("outside-preview-stage.txt").write_text("must not publish\\n")
        (out_dir / "assets" / "linked-secret.txt").symlink_to(Path.cwd() / "outside-preview-stage.txt")
        sys.exit(0)

    if counter == 0:
        (out_dir / "sw.js").write_text("self.skipWaiting();\\n")
        (out_dir / ".well-known").mkdir(parents=True, exist_ok=True)
        (out_dir / ".well-known" / "assetlinks.json").write_text("{}\\n")
        (out_dir / "assets" / "removed.js").write_text("console.log('removed');\\n")
        (out_dir / "assets" / "shape").mkdir(parents=True, exist_ok=True)
        (out_dir / "assets" / "shape" / "chunk.js").write_text("console.log('old shape');\\n")
    else:
        (out_dir / "assets" / "shape").write_text("console.log('new shape');\\n")
        (out_dir / "assets" / "current.js").write_text("console.log('current');\\n")

sys.exit(0)
"""
)
fake_npm.chmod(0o755)
existing_path = env.get("PATH", "")
build_env = {**env, "PATH": str(fake_bin) if not existing_path else str(fake_bin) + os.pathsep + existing_path}
build_command = module.build_frontend_preview_build_command()
build_script = shlex.split(build_command)[2]
build_publish_source = build_script[
    build_script.index("def publish_preview_build(stage_dir: Path) -> None:") : build_script.index("workspace = resolve_current_workspace(Path.cwd())")
]
assert build_publish_source.index('replace_file(deferred_index, live_root / "index.html", tmp_dir)') < build_publish_source.index(
    "prune_live_tree(live_root, stage_dirs, stage_files)"
), build_publish_source
assert "child.is_symlink()" in build_script, build_script
build_result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + build_command],
    cwd=frontend_worktree,
    env=build_env,
    capture_output=True,
    text=True,
)
assert build_result.returncode == 0, build_result.stderr
assert frontend_worktree.joinpath("dist", "index.html").is_file()
assert frontend_worktree.joinpath("dist", "sw.js").is_file()
assert frontend_worktree.joinpath("dist", "assets", "removed.js").is_file()
assert frontend_worktree.joinpath("dist", "assets", "shape").is_dir()

failing_build_script = build_script.replace(
    "def replace_file(src_file: Path, dest_file: Path, tmp_dir: Path) -> None:\n",
    """def replace_file(src_file: Path, dest_file: Path, tmp_dir: Path) -> None:
    if src_file.name == "index.html" and dest_file.name == "index.html" and os.environ.get("FAIL_INDEX_SWAP") == "1":
        raise RuntimeError("simulated index replace failure")
""",
    1,
)
failed_build_result = subprocess.run(
    ["python3", "-c", failing_build_script],
    cwd=frontend_worktree,
    env={**build_env, "FAIL_INDEX_SWAP": "1"},
    capture_output=True,
    text=True,
)
assert failed_build_result.returncode == 1, failed_build_result.stderr
assert "publish failed: simulated index replace failure" in failed_build_result.stderr, failed_build_result.stderr
assert "build 0" in frontend_worktree.joinpath("dist", "index.html").read_text()
assert frontend_worktree.joinpath("dist", "sw.js").is_file()
assert frontend_worktree.joinpath("dist", ".well-known", "assetlinks.json").is_file()
assert frontend_worktree.joinpath("dist", "assets", "removed.js").is_file()
assert frontend_worktree.joinpath("dist", "assets", "current.js").is_file()

recovery_build_result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + build_command],
    cwd=frontend_worktree,
    env=build_env,
    capture_output=True,
    text=True,
)
assert recovery_build_result.returncode == 0, recovery_build_result.stderr
assert "build 2" in frontend_worktree.joinpath("dist", "index.html").read_text()
assert not frontend_worktree.joinpath("dist", "sw.js").exists()
assert not frontend_worktree.joinpath("dist", ".well-known", "assetlinks.json").exists()
assert not frontend_worktree.joinpath("dist", "assets", "removed.js").exists()
assert frontend_worktree.joinpath("dist", "assets", "shape").is_file()
assert frontend_worktree.joinpath("dist", "assets", "current.js").is_file()
assert frontend_worktree.joinpath("npm-vite-api-url.log").read_text() == "https://api-azure-cheetah.preview.secpal.dev\n"

symlink_build_result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + build_command],
    cwd=frontend_worktree,
    env={**build_env, "FAKE_NPM_SYMLINK": "1"},
    capture_output=True,
    text=True,
)
assert symlink_build_result.returncode == 1, symlink_build_result.stderr
assert "staged build output contains symlink: assets/linked-secret.txt" in symlink_build_result.stderr, symlink_build_result.stderr
assert not frontend_worktree.joinpath("dist", "assets", "linked-secret.txt").exists()

# Concurrent preview builds must serialize the complete build and publication
# lifecycle rather than interleaving their staged artifacts.
frontend_worktree.joinpath(".fake-npm-build-count").write_text("0")
concurrent_builds = [
    subprocess.Popen(
        ["bash", "-c", "set -euo pipefail; " + build_command],
        cwd=frontend_worktree,
        env={**build_env, "FAKE_NPM_BUILD_DELAY": "0.2"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(2)
]
concurrent_results = [process.communicate(timeout=5) for process in concurrent_builds]
assert [process.returncode for process in concurrent_builds] == [0, 0], concurrent_results
assert not frontend_worktree.joinpath(".fake-npm-build-overlap").exists(), concurrent_results
assert frontend_worktree.joinpath(".fake-npm-build-count").read_text() == "2", concurrent_results
assert "build 1" in frontend_worktree.joinpath("dist", "index.html").read_text()

frontend_worktree.joinpath("dist").rename(frontend_worktree / "old-dist")
frontend_worktree.joinpath("live-dist-target").mkdir()
frontend_worktree.joinpath("dist").symlink_to(frontend_worktree / "live-dist-target", target_is_directory=True)
live_symlink_result = subprocess.run(["bash", "-c", "set -euo pipefail; " + build_command], cwd=frontend_worktree, env=build_env, capture_output=True, text=True)
assert live_symlink_result.returncode == 1, live_symlink_result.stderr
assert "publish failed: live preview dist is a symlink" in live_symlink_result.stderr, live_symlink_result.stderr

# Run the resolver portion only (up to subprocess.run) by patching subprocess.run to capture env.
import textwrap as _textwrap
resolver_probe = _textwrap.dedent(f"""
import os
import subprocess
from pathlib import Path

{module.build_linked_workspace_resolver_source()}

workspace = resolve_current_workspace(Path.cwd())
api_workspace = resolve_linked_workspace("SecPal/api", workspace)
print(f"VITE_API_URL=https://api-{{api_workspace}}.preview.secpal.dev")
""").strip()
probe_result = subprocess.run(
    ["python3", "-c", resolver_probe],
    cwd=frontend_worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert "VITE_API_URL=https://api-azure-cheetah.preview.secpal.dev" in probe_result.stdout, probe_result.stdout

watch_command = module.build_frontend_preview_build_watch_command()
watch_script = shlex.split(watch_command)[2]
watch_publish_source = watch_script[
    watch_script.index("def publish_preview_build(stage_dir: Path) -> None:") : watch_script.index("def run_build()")
]
run_build_source = watch_script[watch_script.index("def run_build()") :]
assert 'api_url = f"https://api-' not in watch_script, watch_script
assert 'workspace = resolve_current_workspace(Path.cwd())' in run_build_source, run_build_source
assert 'api_workspace = resolve_linked_workspace("SecPal/api", workspace)' in run_build_source, run_build_source
assert '--outDir' in run_build_source, run_build_source
assert 'publish_preview_build(stage_dir)' in run_build_source, run_build_source
assert 'Path("dist")' in watch_script, watch_script
assert 'Path("node_modules/.package-lock.json")' in watch_script, watch_script
assert 'Path("node_modules/.bin/cross-env")' not in watch_script, watch_script
assert 'Path("node_modules/.bin/vite")' not in watch_script, watch_script
assert watch_publish_source.index('replace_file(deferred_index, live_root / "index.html", tmp_dir)') < watch_publish_source.index(
    "prune_live_tree(live_root, stage_dirs, stage_files)"
), watch_publish_source
assert "child.is_symlink()" in watch_script, watch_script

# The watcher can race setup-time npm ci. Dependency installation completes
# independently after the initial missing-command failure and must trigger one
# retry via npm's stable hidden lockfile, without a source edit.
frontend_worktree.joinpath(".fake-npm-build-count").write_text("0")
frontend_worktree.joinpath("dist").unlink()
shutil.rmtree(frontend_worktree / "node_modules", ignore_errors=True)
bounded_watch_script = watch_script.replace("while True:\n", "for _watch_iteration in range(8):\n", 1).replace(
    "    time.sleep(1)",
    "    time.sleep(0.1)",
    1,
)
watch_retry_process = subprocess.Popen(
    ["python3", "-c", bounded_watch_script],
    cwd=frontend_worktree,
    env={**build_env, "FAKE_NPM_FAIL_WITHOUT_BUILD_BINARIES": "1"},
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
for _ in range(20):
    if frontend_worktree.joinpath(".fake-npm-build-count").read_text() == "1":
        break
    time.sleep(0.05)
else:
    watch_retry_process.kill()
    raise AssertionError("watcher did not attempt the initial build")

frontend_worktree.joinpath("node_modules").mkdir(exist_ok=True)
frontend_worktree.joinpath("node_modules/.bin").mkdir(exist_ok=True)
frontend_worktree.joinpath("node_modules/.bin/cross-env").write_text("ready\\n")
frontend_worktree.joinpath("node_modules/.bin/vite").write_text("ready\\n")
time.sleep(0.2)
assert frontend_worktree.joinpath(".fake-npm-build-count").read_text() == "1"
frontend_worktree.joinpath("node_modules/.package-lock.json").write_text("{}\\n")
_watch_retry_stdout, watch_retry_stderr = watch_retry_process.communicate(timeout=5)
assert watch_retry_process.returncode == 0, watch_retry_stderr
assert frontend_worktree.joinpath(".fake-npm-build-count").read_text() == "2", watch_retry_stderr
assert frontend_worktree.joinpath("dist/index.html").exists(), watch_retry_stderr
assert frontend_worktree.joinpath("dist/index.html").read_text() == "<!doctype html>build 1\n", watch_retry_stderr
assert "waiting for dependency installation or a source change" in watch_retry_stderr, watch_retry_stderr

# Permanently unavailable dependencies must wait for a subsequent change, not
# spin through repeated exit-127 builds.
frontend_worktree.joinpath(".fake-npm-build-count").write_text("0")
frontend_worktree.joinpath("node_modules/.package-lock.json").unlink()
watch_no_retry_result = subprocess.run(
    ["python3", "-c", bounded_watch_script],
    cwd=frontend_worktree,
    env={**build_env, "FAKE_NPM_FAIL_ALWAYS_BUILD_127": "1"},
    capture_output=True,
    text=True,
    timeout=5,
)
assert watch_no_retry_result.returncode == 0, watch_no_retry_result.stderr
assert frontend_worktree.joinpath(".fake-npm-build-count").read_text() == "1", watch_no_retry_result.stderr

# build_frontend_preview_playwright_command: assert linked API workspace is used in PLAYWRIGHT_API_BASE_URL
playwright_probe = _textwrap.dedent(f"""
import os
import subprocess
from pathlib import Path

{module.build_linked_workspace_resolver_source()}

workspace = resolve_current_workspace(Path.cwd())
api_workspace = resolve_linked_workspace("SecPal/api", workspace)
print(f"PLAYWRIGHT_BASE_URL=https://frontend-{{workspace}}.preview.secpal.dev")
print(f"PLAYWRIGHT_API_BASE_URL=https://api-{{api_workspace}}.preview.secpal.dev")
""").strip()
playwright_probe_result = subprocess.run(
    ["python3", "-c", playwright_probe],
    cwd=frontend_worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert "PLAYWRIGHT_BASE_URL=https://frontend-azure-cheetah.preview.secpal.dev" in playwright_probe_result.stdout, playwright_probe_result.stdout
assert "PLAYWRIGHT_API_BASE_URL=https://api-azure-cheetah.preview.secpal.dev" in playwright_probe_result.stdout, playwright_probe_result.stdout
PY

# normalize_registered_workspace_path must update the matched worktree row even when
# Polyscope stored a different path string that resolves to the same directory.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sqlite3
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "normalize-registered-worktree-fixture"
db_path = fixture / "polyscope.db"
worktree_path = fixture / "clones" / "api12345" / "azure-cheetah-165552b7"
registered_path = worktree_path.parent / "registered-worktree"
normalized_path = worktree_path.parent / "azure-cheetah"
linked_frontend_path = fixture / "clones" / "fe123456" / "azure-cheetah"
worktree_path.mkdir(parents=True)
linked_frontend_path.mkdir(parents=True)
registered_path.symlink_to(worktree_path.name)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

with sqlite3.connect(db_path) as connection:
    connection.executescript(
        """
        create table repositories (
            id text primary key,
            name text not null,
            path text not null
        );
        create table worktrees (
            id text primary key,
            repo_id text not null,
            branch text not null,
            path text not null,
            created_at text default (datetime('now')) not null
        );
        create table worktree_links (
            worktree_id text not null,
            linked_worktree_id text not null,
            created_at text default (datetime('now')) not null
        )
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [
            ("api12345", "SecPal/api", str(fixture / "source-api")),
            ("fe123456", "SecPal/frontend", str(fixture / "source-frontend")),
        ],
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        ("frontend-worktree", "fe123456", "azure-cheetah", str(linked_frontend_path)),
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        ("api-worktree", "api12345", "not-the-workspace", str(registered_path)),
    )
    connection.execute(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        ("api-worktree", "frontend-worktree"),
    )

module.normalize_registered_workspace_path(worktree_path, db_path=db_path)

with sqlite3.connect(db_path) as connection:
    stored_path = connection.execute(
        "select path from worktrees where id = ?",
        ("api-worktree",),
    ).fetchone()[0]

assert stored_path == str(worktree_path.parent / "azure-cheetah"), stored_path
normalized_path = worktree_path.parent / "azure-cheetah"
assert normalized_path.is_symlink(), normalized_path
assert normalized_path.resolve() == worktree_path.resolve(), normalized_path.resolve()
PY

# Git branch metadata must not be used as the preview workspace name; hostnames
# and aliases are derived from the Polyscope workspace path instead.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sqlite3
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "branch-workspace-slug-fixture"
db_path = fixture / "polyscope.db"
worktree_path = fixture / "clones" / "api12345" / "fix-polyscope-preview-env-setup"
worktree_path.mkdir(parents=True)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

with sqlite3.connect(db_path) as connection:
    connection.execute(
        """
        create table worktrees (
            id text primary key,
            repo_id text not null,
            branch text not null,
            path text not null,
            created_at text default (datetime('now')) not null
        )
        """
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        ("api-worktree", "api12345", "not-the-workspace", str(worktree_path)),
    )

workspace_name = module.resolve_current_workspace_name(worktree_path, db_path=db_path)
assert workspace_name == "fix-polyscope-preview-env-setup", workspace_name
updates = module.build_api_preview_env_updates(workspace_name)
assert updates["APP_URL"] == "https://api-fix-polyscope-preview-env-setup.preview.secpal.dev", updates
assert "not-the-workspace" not in updates["APP_URL"], updates
preview_updates = module.build_api_preview_env_updates(workspace_name, worktree_path=worktree_path)
assert preview_updates["KEK_PATH"] == str((worktree_path / "storage" / "app" / "keys" / "kek.key").resolve()), preview_updates
module.ensure_workspace_alias(worktree_path, db_path=db_path)
alias_path = worktree_path.parent / workspace_name
assert alias_path.exists(), alias_path
assert alias_path.resolve() == worktree_path.resolve(), alias_path.resolve()
assert not (worktree_path.parent / "Codex").exists(), list(worktree_path.parent.iterdir())
PY

# Workspace fallback names must drop the legacy eight-hex suffix for preview
# hostnames and aliases.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "real-eight-hex-workspace-fixture"
worktree_path = fixture / "clones" / "api12345" / "fix-deadbeef"
worktree_path.mkdir(parents=True)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace_name = module.resolve_current_workspace_name(worktree_path)
assert workspace_name == "fix", workspace_name
PY

# Distinct legacy hash-suffixed sibling worktrees must keep unique preview
# slugs so they do not share databases, hostnames, or aliases.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "duplicate-legacy-workspace-fixture"
first_worktree = fixture / "clones" / "api12345" / "azure-cheetah-11111111"
second_worktree = fixture / "clones" / "api12345" / "azure-cheetah-22222222"
first_worktree.mkdir(parents=True)
second_worktree.mkdir(parents=True)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

first_workspace = module.resolve_current_workspace_name(first_worktree)
second_workspace = module.resolve_current_workspace_name(second_worktree)
assert first_workspace == "azure-cheetah-11111111", first_workspace
assert second_workspace == "azure-cheetah-22222222", second_workspace
assert first_workspace != second_workspace
assert module.build_api_preview_env_updates(first_workspace)["APP_URL"] != module.build_api_preview_env_updates(second_workspace)["APP_URL"]
assert module.build_preview_database_name("secpal", first_workspace) != module.build_preview_database_name("secpal", second_workspace)

module.ensure_workspace_alias(first_worktree)
module.ensure_workspace_alias(second_worktree)
assert not (first_worktree.parent / "azure-cheetah").exists()
PY

# Distinct worktrees whose names normalize to the same slug without using the
# legacy eight-hex suffix must still resolve to unique preview workspaces.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import hashlib
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "normalized-workspace-collision-fixture"
first_worktree = fixture / "clones" / "api12345" / "Feature A"
second_worktree = fixture / "clones" / "api12345" / "feature_a"
first_worktree.mkdir(parents=True)
second_worktree.mkdir(parents=True)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

first_workspace = module.resolve_current_workspace_name(first_worktree)
second_workspace = module.resolve_current_workspace_name(second_worktree)
assert first_workspace == "feature-a-" + hashlib.sha1("Feature A".encode("utf-8")).hexdigest()[:8], first_workspace
assert second_workspace == "feature-a-" + hashlib.sha1("feature_a".encode("utf-8")).hexdigest()[:8], second_workspace
assert first_workspace != second_workspace
assert module.build_api_preview_env_updates(first_workspace)["APP_URL"] != module.build_api_preview_env_updates(second_workspace)["APP_URL"]
assert module.build_preview_database_name("secpal", first_workspace) != module.build_preview_database_name("secpal", second_workspace)
PY

# Linked-workspace resolution must preserve the colliding hashed slug when the
# Polyscope DB stores a normalized alias path for that linked worktree.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import sqlite3
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "linked-workspace-collision-fixture"
db_path = fixture / "polyscope.db"
frontend_worktree = fixture / "clones" / "fe123456" / "azure-cheetah"
first_api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-11111111"
second_api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-22222222"
linked_api_alias = fixture / "clones" / "api12345" / "azure-cheetah"
frontend_worktree.mkdir(parents=True)
first_api_worktree.mkdir(parents=True)
second_api_worktree.mkdir(parents=True)
linked_api_alias.symlink_to(first_api_worktree.name)

with sqlite3.connect(db_path) as connection:
    connection.executescript(
        """
        create table repositories (id text primary key, name text not null, path text not null);
        create table worktrees (id text primary key, repo_id text not null, path text not null, created_at text default (datetime('now')) not null);
        create table worktree_links (worktree_id text not null, linked_worktree_id text not null, created_at text default (datetime('now')) not null);
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [
            ("api12345", "SecPal/api", str(fixture / "source-api")),
            ("fe123456", "SecPal/frontend", str(fixture / "source-frontend")),
        ],
    )
    connection.executemany(
        "insert into worktrees (id, repo_id, path) values (?, ?, ?)",
        [
            ("frontend-worktree", "fe123456", str(frontend_worktree)),
            ("api-worktree", "api12345", str(linked_api_alias)),
        ],
    )
    connection.execute(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        ("frontend-worktree", "api-worktree"),
    )

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

linked_api_workspace = module.resolve_linked_workspace_name(
    frontend_worktree,
    "SecPal/api",
    db_path=db_path,
)
assert linked_api_workspace == "azure-cheetah-11111111", linked_api_workspace

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(db_path)
resolver_probe = (
    "from pathlib import Path\n\n"
    f"{module.build_linked_workspace_resolver_source()}\n\n"
    "workspace = resolve_current_workspace(Path.cwd())\n"
    'print(resolve_linked_workspace("SecPal/api", workspace))\n'
)
probe_result = subprocess.run(
    ["python3", "-c", resolver_probe],
    cwd=frontend_worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert probe_result.stdout.strip() == "azure-cheetah-11111111", probe_result.stdout

current_workspace_probe = (
    "from pathlib import Path\n\n"
    f"{module.build_linked_workspace_resolver_source()}\n\n"
    "print(resolve_current_workspace(Path.cwd()))\n"
)
current_workspace_result = subprocess.run(
    ["python3", "-c", current_workspace_probe],
    cwd=first_api_worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert current_workspace_result.stdout.strip() == "azure-cheetah-11111111", current_workspace_result.stdout
PY

# Generated inline resolvers must not create a new SQLite file when the
# Polyscope database path is missing.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "missing-polyscope-db-fixture"
worktree = fixture / "clones" / "fe123456" / "steady-otter"
missing_db = fixture / "missing.db"
worktree.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(missing_db)
probe = (
    "from pathlib import Path\n\n"
    f"{module.build_linked_workspace_resolver_source()}\n\n"
    "print(resolve_current_workspace(Path.cwd()))\n"
)
result = subprocess.run(
    ["python3", "-c", probe],
    cwd=worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert result.stdout.strip() == "steady-otter", result.stdout
assert not missing_db.exists(), missing_db
PY

# Linked-workspace resolution must stay compatible with older Polyscope DBs
# whose `worktrees` table lacks an unused `branch` column.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import sqlite3
import subprocess
import sys
import textwrap

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "legacy-worktrees-schema-fixture"
db_path = fixture / "polyscope.db"
frontend_worktree = fixture / "clones" / "fe123456" / "azure-cheetah"
api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-165552b7"
source_api = fixture / "source-api"
frontend_worktree.mkdir(parents=True)
api_worktree.mkdir(parents=True)
source_api.mkdir(parents=True)
source_api.joinpath(".env").write_text(
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=sqlite\n"
)
api_worktree.joinpath(".env").write_text(source_api.joinpath(".env").read_text())

with sqlite3.connect(db_path) as connection:
    connection.executescript(
        """
        create table repositories (id text primary key, name text not null, path text not null);
        create table worktrees (id text primary key, repo_id text not null, path text not null, created_at text default (datetime('now')) not null);
        create table worktree_links (worktree_id text not null, linked_worktree_id text not null, created_at text default (datetime('now')) not null);
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [
            ("api12345", "SecPal/api", str(source_api)),
            ("fe123456", "SecPal/frontend", str(fixture / "source-frontend")),
        ],
    )
    connection.executemany(
        "insert into worktrees (id, repo_id, path) values (?, ?, ?)",
        [
            ("api-worktree", "api12345", str(api_worktree)),
            ("frontend-worktree", "fe123456", str(frontend_worktree)),
        ],
    )
    connection.executemany(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        [
            ("frontend-worktree", "api-worktree"),
            ("api-worktree", "frontend-worktree"),
        ],
    )

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

module.ensure_workspace_alias(api_worktree)

linked_api_workspace = module.resolve_linked_workspace_name(
    frontend_worktree,
    "SecPal/api",
    db_path=db_path,
)
assert linked_api_workspace == "azure-cheetah", linked_api_workspace

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(db_path)
resolver_probe = (
    "import os\n"
    "import subprocess\n"
    "from pathlib import Path\n\n"
    f"{module.build_linked_workspace_resolver_source()}\n\n"
    "workspace = resolve_current_workspace(Path.cwd())\n"
    'api_workspace = resolve_linked_workspace("SecPal/api", workspace)\n'
    'print(f"VITE_API_URL=https://api-{api_workspace}.preview.secpal.dev")\n'
)
probe_result = subprocess.run(
    ["python3", "-c", resolver_probe],
    cwd=frontend_worktree,
    env=env,
    capture_output=True,
    text=True,
    check=True,
)
assert "VITE_API_URL=https://api-azure-cheetah.preview.secpal.dev" in probe_result.stdout, probe_result.stdout
PY

# Provisioned worktrees must keep their original preview slug even when the
# physical workspace directory is renamed later.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import json
import pathlib
import sqlite3
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "renamed-provisioned-workspace-fixture"
db_path = fixture / "polyscope.db"
original_alias = fixture / "clones" / "api12345" / "bubbly-salmon"
renamed_worktree = fixture / "clones" / "api12345" / "fix-db-password-check"
renamed_worktree.mkdir(parents=True, exist_ok=True)
renamed_worktree.joinpath(".polyscope-secpal-provisioned.json").write_text(
    json.dumps(
        {
            "repo": "api",
            "workspace": "bubbly-salmon",
            "physical_workspace": "bubbly-salmon",
            "setup_hash": "fixture",
            "provisioned_at": "2026-07-06T00:00:00+00:00",
        }
    )
)

with sqlite3.connect(db_path) as connection:
    connection.execute(
        """
        create table worktrees (
            id text primary key,
            repo_id text not null,
            branch text not null,
            path text not null,
            created_at text default (datetime('now')) not null
        )
        """
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        ("api-worktree", "api12345", "fix-db-password-check", str(renamed_worktree)),
    )

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace_name = module.resolve_current_workspace_name(renamed_worktree, db_path=db_path)
assert workspace_name == "bubbly-salmon", workspace_name
preview_updates = module.build_api_preview_env_updates(workspace_name)
assert preview_updates["APP_URL"] == "https://api-bubbly-salmon.preview.secpal.dev", preview_updates

module.ensure_workspace_alias(renamed_worktree, db_path=db_path)
assert original_alias.is_symlink(), original_alias
assert original_alias.resolve() == renamed_worktree.resolve(), original_alias.resolve()
PY

# Provision markers are worktree-local state and must not be able to inject
# path components into aliases or preview hostnames.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import json
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "unsafe-provision-marker-fixture"
worktree = fixture / "clones" / "api12345" / "feature-branch"
outside_alias = fixture / "clones" / "outside-alias"
safe_alias = worktree.parent / "outside-alias"
worktree.mkdir(parents=True, exist_ok=True)
worktree.joinpath(".polyscope-secpal-provisioned.json").write_text(
    json.dumps({"workspace": "../outside-alias"})
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace_name = module.resolve_current_workspace_name(worktree)
assert workspace_name == "outside-alias", workspace_name
preview_updates = module.build_api_preview_env_updates(workspace_name)
assert preview_updates["APP_URL"] == "https://api-outside-alias.preview.secpal.dev", preview_updates

module.ensure_workspace_alias(worktree)
assert safe_alias.is_symlink(), safe_alias
assert safe_alias.resolve() == worktree.resolve(), safe_alias.resolve()
assert not outside_alias.exists(), outside_alias
PY

# Linked-workspace resolution and generated callable preview URLs must keep the
# original provisioned slug after a linked worktree directory rename.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import json
import os
import pathlib
import sqlite3
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "renamed-linked-workspace-fixture"
db_path = fixture / "polyscope.db"
frontend_worktree = fixture / "clones" / "fe123456" / "inspect-session-check"
renamed_api_worktree = fixture / "clones" / "api12345" / "fix-db-password-check"
frontend_worktree.mkdir(parents=True, exist_ok=True)
renamed_api_worktree.mkdir(parents=True, exist_ok=True)
renamed_api_worktree.joinpath(".polyscope-secpal-provisioned.json").write_text(
    json.dumps(
        {
            "repo": "api",
            "workspace": "bubbly-salmon",
            "physical_workspace": "bubbly-salmon",
            "setup_hash": "fixture",
            "provisioned_at": "2026-07-06T00:00:00+00:00",
        }
    )
)
frontend_worktree.joinpath(".env.local").write_text("VITE_API_URL=https://api.secpal.dev\n")

with sqlite3.connect(db_path) as connection:
    connection.executescript(
        """
        create table repositories (id text primary key, name text not null, path text not null);
        create table worktrees (id text primary key, repo_id text not null, path text not null, created_at text default (datetime('now')) not null);
        create table worktree_links (worktree_id text not null, linked_worktree_id text not null, created_at text default (datetime('now')) not null);
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [
            ("api12345", "SecPal/api", str(fixture / "source-api")),
            ("fe123456", "SecPal/frontend", str(fixture / "source-frontend")),
        ],
    )
    connection.executemany(
        "insert into worktrees (id, repo_id, path) values (?, ?, ?)",
        [
            ("frontend-worktree", "fe123456", str(frontend_worktree)),
            ("api-worktree", "api12345", str(renamed_api_worktree)),
        ],
    )
    connection.execute(
        "insert into worktree_links (worktree_id, linked_worktree_id) values (?, ?)",
        ("frontend-worktree", "api-worktree"),
    )

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

linked_api_workspace = module.resolve_linked_workspace_name(
    frontend_worktree,
    "SecPal/api",
    db_path=db_path,
)
assert linked_api_workspace == "bubbly-salmon", linked_api_workspace

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(db_path)
subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_frontend_preview_env_setup_command()],
    cwd=frontend_worktree,
    env=env,
    check=True,
)
frontend_env = frontend_worktree.joinpath(".env.local").read_text()
assert "VITE_API_URL=https://api-bubbly-salmon.preview.secpal.dev" in frontend_env, frontend_env
assert "fix-db-password-check" not in frontend_env, frontend_env
PY

# Legacy hash-suffixed worktree directory names must not leak into preview hostnames
# when the Polyscope DB and git branch are unavailable.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace" "$REPO_ROOT"
import importlib.util
import os
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
repo_root = pathlib.Path(sys.argv[3])
fixture = workspace / "legacy-preview-hostname-fixture"
source_api = fixture / "source-api"
api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-165552b7"
frontend_worktree = fixture / "clones" / "fe123456" / "azure-cheetah-165552b7"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
frontend_worktree.mkdir(parents=True, exist_ok=True)
source_env = (
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=sqlite\n"
)
source_api.joinpath(".env.example").write_text(source_env)
source_api.joinpath(".env").write_text(source_env)
frontend_worktree.joinpath(".env.local").write_text("VITE_API_URL=https://api.secpal.dev\n")

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace_name = module.resolve_current_workspace_name(api_worktree)
assert workspace_name == "azure-cheetah", workspace_name

module.ensure_workspace_alias(api_worktree)
workspace_name_with_alias = module.resolve_current_workspace_name(api_worktree)
assert workspace_name_with_alias == "azure-cheetah", workspace_name_with_alias

ready, _ = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready
api_env = api_worktree.joinpath(".env").read_text()
assert "https://api-azure-cheetah.preview.secpal.dev" in api_env, api_env
assert "https://api-azure-cheetah-165552b7.preview.secpal.dev" not in api_env, api_env

subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_frontend_preview_env_setup_command()],
    cwd=frontend_worktree,
    env={k: v for k, v in os.environ.items() if k != "POLYSCOPE_DB_PATH"},
    check=True,
)
frontend_env = frontend_worktree.joinpath(".env.local").read_text()
assert "https://api-azure-cheetah.preview.secpal.dev" in frontend_env, frontend_env
assert "https://api-azure-cheetah-165552b7.preview.secpal.dev" not in frontend_env, frontend_env

repo_spec_frontend = workspace / "repo-spec-root" / "frontend"
(repo_spec_frontend / ".github").mkdir(parents=True)
(repo_spec_frontend / ".markdownlint.json").write_text(
    (repo_root / ".markdownlint.json").read_text()
)
(repo_spec_frontend / "AGENTS.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Frontend Runtime Instructions\n"
)
(repo_spec_frontend / ".github" / "copilot-instructions.md").write_text(
    "<!--\n"
    "SPDX-FileCopyrightText: 2026 SecPal\n"
    "SPDX-License" "-Identifier: CC0-1.0\n"
    "-->\n\n"
    "# Frontend Review Profile\n"
)
repo_specs = module.build_repo_specs(workspace / "repo-spec-root")
rendered_local_config = module.render_worktree_local_config(repo_specs["frontend"], frontend_worktree)
assert "https://frontend-azure-cheetah.preview.secpal.dev" in rendered_local_config, rendered_local_config
assert "https://frontend-azure-cheetah-165552b7.preview.secpal.dev" not in rendered_local_config, rendered_local_config
PY

# ensure_api_worktree_ready must build a missing API worktree .env from the
# source template, carry forward local base values, and then rewrite
# preview-facing values for the worktree.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "source-env-secret-fixture" / "source-api"
api_worktree = workspace / "source-env-secret-fixture" / "clones" / "api12345" / "attacker-pr"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=sqlite\n"
    "DB_DATABASE=/tmp/template.sqlite\n"
    "DB_PASSWORD=\n"
    "APP_KEY=\n"
    "KEK_PATH=/template/kek\n"
)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=sqlite\n"
    "DB_DATABASE=/tmp/preview.sqlite\n"
    "DB_PASSWORD=prod-secret-password\n"
    "APP_KEY=base64:SOURCE_APP_KEY_SHOULD_NOT_LEAVE_SOURCE\n"
    "KEK_PATH=/runtime/local-kek\n"
    "EXTRA_SECRET=do-not-copy-this-source-only-value\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

ready, preview_storage_target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert preview_storage_target is None
worktree_env = api_worktree.joinpath(".env").read_text()
assert "APP_URL=https://api-attacker-pr.preview.secpal.dev" in worktree_env, worktree_env
assert "FRONTEND_URL=https://frontend-attacker-pr.preview.secpal.dev" in worktree_env, worktree_env
assert "DB_DATABASE=/tmp/preview.sqlite" in worktree_env, worktree_env
assert "DB_PASSWORD=prod-secret-password" not in worktree_env, worktree_env
assert "DB_PASSWORD=\n" in worktree_env or worktree_env.endswith("DB_PASSWORD="), worktree_env
assert "KEK_PATH=/runtime/local-kek" not in worktree_env, worktree_env
assert f"KEK_PATH={api_worktree.joinpath('storage/app/keys/kek.key').resolve()}" in worktree_env, worktree_env
assert "APP_KEY=base64:SOURCE_APP_KEY_SHOULD_NOT_LEAVE_SOURCE" not in worktree_env, worktree_env
assert "APP_KEY=\n" not in worktree_env and not worktree_env.endswith("APP_KEY="), worktree_env
assert "APP_KEY=base64:" in worktree_env, worktree_env
assert "EXTRA_SECRET=do-not-copy-this-source-only-value" not in worktree_env, worktree_env
PY

# build_api_worktree_env_template must keep source PostgreSQL passwords out of
# generated worktree templates even when the source checkout uses one locally.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "source-pgsql-env-fixture" / "source-api"
source_api.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
    "APP_KEY=\n"
    "KEK_PATH=/template/kek\n"
)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=preview-db-password\n"
    "APP_KEY=base64:SOURCE_APP_KEY_SHOULD_NOT_LEAVE_SOURCE\n"
    "KEK_PATH=/runtime/local-kek\n"
    "EXTRA_SECRET=do-not-copy-this-source-only-value\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

template = module.build_api_worktree_env_template(
    source_api,
    source_env_path=source_api / ".env",
)
assert "DB_PASSWORD=\n" in template or template.endswith("DB_PASSWORD="), template
assert "APP_KEY=base64:SOURCE_APP_KEY_SHOULD_NOT_LEAVE_SOURCE" not in template, template
assert "KEK_PATH=/runtime/local-kek" not in template, template
assert "KEK_PATH=/template/kek" in template, template
assert "EXTRA_SECRET=do-not-copy-this-source-only-value" not in template, template
PY

# build_api_worktree_env_template must keep a template PostgreSQL password
# when the source checkout carries a blank local DB_PASSWORD assignment.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "source-pgsql-empty-password-fixture" / "source-api"
source_api.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=preview-db-password\n"
    "APP_KEY=\n"
)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

template = module.build_api_worktree_env_template(
    source_api,
    source_env_path=source_api / ".env",
)
assert "DB_PASSWORD=preview-db-password" in template, template
PY

# upsert_env_assignments must preserve backslashes in replacement values instead
# of letting re.sub interpret them as replacement escapes.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

updated = module.upsert_env_assignments(
    "DB_PASSWORD=\n",
    {"DB_PASSWORD": r"secret\path\1"},
)
assert r"DB_PASSWORD=secret\path\1" in updated, updated

round_trip_path = workspace / "roundtrip.env"
round_trip_path.write_text('DB_PASSWORD="secret\\\\path\\\\1 #\\"quoted\\""\n')
round_trip = module.load_env_assignments(round_trip_path)
assert round_trip["DB_PASSWORD"] == 'secret\\path\\1 #"quoted"', round_trip
PY

# ensure_api_worktree_ready must persist the PostgreSQL password into preview
# API worktree .env files so PHP-FPM runtime requests can connect after
# provisioning, while still using that same password during preview database
# provisioning.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "transient-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "transient-pgsql-password-fixture" / "clones" / "api12345" / "quiet-bear"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-only-password\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return True

def fake_ensure_postgres_preview_database(env_values, base_database, preview_database):
    calls.append(("create", env_values["DB_PASSWORD"], base_database, preview_database))

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_database = fake_ensure_postgres_preview_database

ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert calls == [
    ("role", "source-only-password", "secpal"),
    ("create", "source-only-password", "secpal", "secpal__preview__quiet_bear"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=source-only-password" in worktree_env, worktree_env

source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=rotated-source-password\n"
)
calls.clear()
ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert calls == [
    ("role", "rotated-source-password", "secpal"),
    ("create", "rotated-source-password", "secpal", "secpal__preview__quiet_bear"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=rotated-source-password" in worktree_env, worktree_env
assert "DB_PASSWORD=source-only-password" not in worktree_env, worktree_env
PY

# ensure_api_worktree_ready must preserve source-managed PostgreSQL passwords
# that require quoted env encoding across later reruns.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "escaped-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "escaped-pgsql-password-fixture" / "clones" / "api12345" / "quiet-bear"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_password = 'secret\\path\\1 #"quoted"'
escaped_source_password = source_password.replace("\\", "\\\\").replace('"', '\\"')
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    f'DB_PASSWORD="{escaped_source_password}"\n'
)
api_worktree.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return True

def fake_ensure_postgres_preview_database(env_values, base_database, preview_database):
    calls.append(("create", env_values["DB_PASSWORD"], base_database, preview_database))

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_database = fake_ensure_postgres_preview_database

ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert calls == [
    ("role", source_password, "secpal"),
    ("create", source_password, "secpal", "secpal__preview__quiet_bear"),
    ("role", source_password, "secpal"),
    ("create", source_password, "secpal", "secpal__preview__quiet_bear"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert 'DB_PASSWORD="secret\\\\path\\\\1 #\\"quoted\\""' in worktree_env, worktree_env
PY

# ensure_api_worktree_ready must not overwrite an explicitly configured
# worktree PostgreSQL password with the source checkout password.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import hashlib
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "explicit-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "explicit-pgsql-password-fixture" / "clones" / "api12345" / "quiet-bear"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-password\n"
)
api_worktree.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=worktree-password\n"
    "POLYSCOPE_DB_PASSWORD_SOURCE=source\n"
    f"POLYSCOPE_DB_PASSWORD_SOURCE_SHA256={hashlib.sha256('source-password'.encode('utf-8')).hexdigest()}\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return True

def fake_ensure_postgres_preview_database(env_values, base_database, preview_database):
    calls.append(("create", env_values["DB_PASSWORD"], base_database, preview_database))

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_database = fake_ensure_postgres_preview_database

ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert calls == [
    ("role", "worktree-password", "secpal"),
    ("create", "worktree-password", "secpal", "secpal__preview__quiet_bear"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=worktree-password" in worktree_env, worktree_env
assert "DB_PASSWORD=source-password" not in worktree_env, worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE=\n" in worktree_env or worktree_env.endswith("POLYSCOPE_DB_PASSWORD_SOURCE="), worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE_SHA256=\n" in worktree_env or worktree_env.endswith("POLYSCOPE_DB_PASSWORD_SOURCE_SHA256="), worktree_env
PY

# ensure_api_worktree_ready must clear a source-managed worktree password when
# the source checkout clears DB_PASSWORD.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import hashlib
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "cleared-source-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "cleared-source-pgsql-password-fixture" / "clones" / "api12345" / "quiet-bear"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)
source_hash = hashlib.sha256("source-password".encode("utf-8")).hexdigest()
api_worktree.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-password\n"
    "POLYSCOPE_DB_PASSWORD_SOURCE=source\n"
    f"POLYSCOPE_DB_PASSWORD_SOURCE_SHA256={source_hash}\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return True

def fake_ensure_postgres_preview_database(env_values, base_database, preview_database):
    calls.append(("create", env_values["DB_PASSWORD"], base_database, preview_database))

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_database = fake_ensure_postgres_preview_database

ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert calls == [
    ("role", "", "secpal"),
    ("create", "", "secpal", "secpal__preview__quiet_bear"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=\n" in worktree_env or worktree_env.endswith("DB_PASSWORD="), worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE=\n" in worktree_env or worktree_env.endswith("POLYSCOPE_DB_PASSWORD_SOURCE="), worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE_SHA256=\n" in worktree_env or worktree_env.endswith("POLYSCOPE_DB_PASSWORD_SOURCE_SHA256="), worktree_env
PY

# ensure_api_worktree_ready must persist the PostgreSQL password into schema-mode
# preview .env values without leaking it through generated DB_URL values.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "schema-password-leak-fixture" / "source-api"
api_worktree = workspace / "schema-password-leak-fixture" / "clones" / "api12345" / "careful-otter"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-only-password\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return False

def fake_ensure_postgres_preview_schema(env_values, base_database, preview_schema):
    calls.append(("schema", env_values["DB_PASSWORD"], base_database, preview_schema))

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_schema = fake_ensure_postgres_preview_schema

ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "schema:secpal:secpal__preview__careful_otter", target
assert calls == [
    ("role", "source-only-password", "secpal"),
    ("schema", "source-only-password", "secpal", "secpal__preview__careful_otter"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=source-only-password" in worktree_env, worktree_env
assert "source-only-password@" not in worktree_env, worktree_env
assert "DB_URL=postgresql://secpal_app@127.0.0.1:5432/secpal?search_path=secpal__preview__careful_otter" in worktree_env, worktree_env

calls.clear()
ready, target = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
assert target == "schema:secpal:secpal__preview__careful_otter", target
assert calls == [
    ("role", "source-only-password", "secpal"),
    ("schema", "source-only-password", "secpal", "secpal__preview__careful_otter"),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=source-only-password" in worktree_env, worktree_env
assert "source-only-password@" not in worktree_env, worktree_env
assert "DB_URL=postgresql://secpal_app@127.0.0.1:5432/secpal?search_path=secpal__preview__careful_otter" in worktree_env, worktree_env
PY

# refresh_api_worktree must reuse the transient runtime DB password injection
# when the worktree keeps DB_PASSWORD blank but the source checkout does not.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "refresh-transient-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "refresh-transient-pgsql-password-fixture" / "clones" / "api12345" / "quiet-bear"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal__preview__quiet_bear\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-only-password\n"
)
api_worktree.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal__preview__quiet_bear\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
    "POLYSCOPE_PREVIEW_STORAGE_MODE=database\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []
db_calls = []

def fake_postgres_role_can_create_databases(env_values, base_database):
    db_calls.append(("role", env_values["DB_PASSWORD"], base_database))
    return True

def fake_ensure_postgres_preview_database(env_values, base_database, preview_database):
    db_calls.append(("create", env_values["DB_PASSWORD"], base_database, preview_database))

def fake_run_api_worktree_bootstrap_command(worktree_path, command, *, command_env):
    calls.append(
        (
            tuple(command),
            worktree_path,
            command_env["DB_PASSWORD"],
            command_env["PGPASSWORD"],
        )
    )

module.postgres_role_can_create_databases = fake_postgres_role_can_create_databases
module.ensure_postgres_preview_database = fake_ensure_postgres_preview_database
module.run_api_worktree_bootstrap_command = fake_run_api_worktree_bootstrap_command

ready, target = module.refresh_api_worktree(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__quiet_bear", target
assert db_calls == [
    ("role", "source-only-password", "secpal"),
    (
        "create",
        "source-only-password",
        "secpal",
        "secpal__preview__quiet_bear",
    ),
], db_calls
assert calls == [
    (("composer", "install"), api_worktree, "source-only-password", "source-only-password"),
    (("php", "artisan", "config:clear"), api_worktree, "source-only-password", "source-only-password"),
    (("php", "artisan", "migrate:fresh", "--force"), api_worktree, "source-only-password", "source-only-password"),
    (("php", "artisan", "addresses:import", "--if-empty", "--setup-only", "--no-interaction"), api_worktree, "source-only-password", "source-only-password"),
    (("php", "artisan", "db:seed", "--force"), api_worktree, "source-only-password", "source-only-password"),
    (
        ("php", "artisan", "tinker", f"--execute={module.build_api_preview_test_user_tinker_script()}"),
        api_worktree,
        "source-only-password",
        "source-only-password",
    ),
], calls
worktree_env = api_worktree.joinpath(".env").read_text()
assert "DB_PASSWORD=source-only-password" in worktree_env, worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE=source" in worktree_env, worktree_env
assert "POLYSCOPE_DB_PASSWORD_SOURCE_SHA256=" in worktree_env, worktree_env
PY

# Bootstrap output must remain visible while a command is running, while its
# complete transcript remains available to classify a failed seed command.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import builtins
import importlib.util
import pathlib
import subprocess
import sys
from unittest.mock import patch

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

emitted = []
popen_calls = []

class FakeProcess:
    stdout = ["first line\n", "second line\n"]

    def wait(self):
        assert emitted == ["first line\n", "second line\n"], emitted
        return 1

def fake_popen(*args, **kwargs):
    popen_calls.append((args, kwargs))
    return FakeProcess()

with patch.object(module.subprocess, "Popen", side_effect=fake_popen):
    with patch.object(builtins, "print", side_effect=lambda value="", end="\n": emitted.append(value)):
        try:
            module.run_api_worktree_bootstrap_command(
                workspace,
                ["php", "artisan", "db:seed", "--force"],
                command_env={},
            )
        except subprocess.CalledProcessError as error:
            assert error.output == "first line\nsecond line\n", error.output
        else:
            raise AssertionError("expected streamed bootstrap failure")

assert len(popen_calls) == 1, popen_calls
assert popen_calls[0][1]["stdout"] is subprocess.PIPE, popen_calls
assert popen_calls[0][1]["stderr"] is subprocess.STDOUT, popen_calls
PY

# A stale per-worktree KEK cannot unwrap tenant keys left in an isolated
# preview database. Bootstrap must recognize that exact failure, discard only
# the preview key material, and retry once from a fresh preview database.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "tenant-key-recovery-fixture" / "source-api"
api_worktree = workspace / "tenant-key-recovery-fixture" / "clones" / "api12345" / "coral-crow-d6cd6a1f"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env").write_text("DB_CONNECTION=sqlite\n")
kek_path = api_worktree / "storage" / "app" / "keys" / "kek.key"
kek_path.parent.mkdir(parents=True)
kek_path.write_bytes(b"stale-preview-kek")
api_worktree.joinpath(".env").write_text(
    "APP_KEY=base64:preview\n"
    f"KEK_PATH={kek_path}\n"
    "POLYSCOPE_PREVIEW_STORAGE_MODE=database\n"
    "DB_DATABASE=secpal__preview__coral_crow\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []
seed_attempts = [0]

def fake_run_api_worktree_bootstrap_command(worktree_path, command, *, command_env):
    seed_attempts[0] += 1 if command == ["php", "artisan", "db:seed", "--force"] else 0
    calls.append(tuple(command))
    if command == ["php", "artisan", "db:seed", "--force"] and seed_attempts[0] == 1:
        raise subprocess.CalledProcessError(
            1,
            command,
            output=(
                "App\\Models\\TenantKey::loadKek()\n"
                "App\\Models\\TenantKey::unwrapDek()\n"
                "Failed to unwrap DEK\n"
            ),
        )
module.run_api_worktree_bootstrap_command = fake_run_api_worktree_bootstrap_command

ready, target = module.bootstrap_api_worktree(api_worktree, source_api)
assert ready is True
assert target == "database:secpal__preview__coral_crow", target
assert not kek_path.exists(), "recovery must remove the stale isolated-preview KEK"
assert calls == [
    ("composer", "install"),
    ("php", "artisan", "config:clear"),
    ("php", "artisan", "migrate", "--force"),
    ("php", "artisan", "addresses:import", "--if-empty", "--setup-only", "--no-interaction"),
    ("php", "artisan", "db:seed", "--force"),
    ("composer", "install"),
    ("php", "artisan", "config:clear"),
    ("php", "artisan", "migrate:fresh", "--force"),
    ("php", "artisan", "addresses:import", "--if-empty", "--setup-only", "--no-interaction"),
    ("php", "artisan", "db:seed", "--force"),
    ("php", "artisan", "tinker", f"--execute={module.build_api_preview_test_user_tinker_script()}"),
], calls

assert not module.is_recoverable_preview_tenant_key_failure(
    subprocess.CalledProcessError(1, ["php", "artisan", "db:seed", "--force"], output="ordinary seeder failure")
)
assert not module.is_recoverable_preview_tenant_key_failure(
    subprocess.CalledProcessError(
        1,
        ["php", "artisan", "db:seed", "--force"],
        output=(
            "App\\Models\\TenantKey::loadKek()\n"
            "App\\Models\\TenantKey::unwrapDek()\n"
            "Unrelated tenant key failure\n"
        ),
    )
), "stack frames alone must not authorize destructive preview recovery"
kek_path.write_bytes(b"must-not-delete")
assert not module.discard_stale_preview_kek(
    api_worktree,
    module.load_env_assignments(api_worktree / ".env"),
    "database:secpal",
)
assert kek_path.exists(), "recovery must not reset an unisolated database"

api_worktree.joinpath(".env").write_text(
    "APP_KEY=base64:preview\n"
    f"KEK_PATH={kek_path}\n"
    "POLYSCOPE_PREVIEW_STORAGE_MODE=schema\n"
    "POLYSCOPE_PREVIEW_DATABASE_BASE=secpal\n"
    "POLYSCOPE_PREVIEW_SCHEMA=secpal__preview__coral_crow\n"
    "DB_DATABASE=secpal\n"
)
assert module.discard_stale_preview_kek(
    api_worktree,
    module.load_env_assignments(api_worktree / ".env"),
    "schema:secpal:secpal__preview__coral_crow",
)
assert not kek_path.exists(), "schema previews must permit the same isolated KEK recovery"
PY

# run_api_worktree_shell_command must reuse the transient runtime DB password
# injection for long-running preview actions such as the queue worker and scheduler.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "run-transient-pgsql-password-fixture" / "source-api"
api_worktree = workspace / "run-transient-pgsql-password-fixture" / "clones" / "api12345" / "steady-hawk"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal__preview__steady_hawk\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=source-only-password\n"
)
api_worktree.joinpath(".env").write_text(
    "DB_CONNECTION=pgsql\n"
    "DB_HOST=127.0.0.1\n"
    "DB_PORT=5432\n"
    "DB_DATABASE=secpal__preview__steady_hawk\n"
    "DB_USERNAME=secpal_app\n"
    "DB_PASSWORD=\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

calls = []

def fake_chdir(cwd):
    calls.append(("chdir", cwd))

def fake_execvpe(file, args, env):
    calls.append(
        (
            "execvpe",
            file,
            tuple(args),
            env["DB_PASSWORD"],
            env["PGPASSWORD"],
            env["POLYSCOPE_DB_PATH"],
        )
    )
    raise SystemExit(0)

module.os.chdir = fake_chdir
module.os.execvpe = fake_execvpe

db_path = workspace / "runtime-polyscope.db"
try:
    module.run_api_worktree_shell_command(
        api_worktree,
        source_api,
        "php artisan schedule:work",
        db_path=db_path,
    )
except SystemExit as error:
    assert error.code == 0, error

assert calls == [
    ("chdir", api_worktree),
    (
        "execvpe",
        "bash",
        ("bash", "-c", "set -euo pipefail; exec php artisan schedule:work"),
        "source-only-password",
        "source-only-password",
        str(db_path),
    ),
], calls
PY

# ensure_api_worktree_ready must quote generated KEK paths when the worktree
# path contains spaces so dotenv consumers can parse the value correctly.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
source_api = workspace / "quoted-kek-path-fixture" / "source-api"
api_worktree = workspace / "quoted-kek-path-fixture" / "clones" / "api12345" / "Steady Otter"
source_api.mkdir(parents=True, exist_ok=True)
api_worktree.mkdir(parents=True, exist_ok=True)
source_api.joinpath(".env.example").write_text(
    "APP_URL=https://api.secpal.dev\n"
    "FRONTEND_URL=https://app.secpal.dev\n"
    "DB_CONNECTION=sqlite\n"
    "KEK_PATH=/template/kek\n"
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

ready, _ = module.ensure_api_worktree_ready(api_worktree, source_api)
assert ready is True
expected = api_worktree.joinpath("storage/app/keys/kek.key").resolve()
worktree_env = api_worktree.joinpath(".env").read_text()
assert f'KEK_PATH="{expected}"' in worktree_env, worktree_env
assert module.load_env_assignments(api_worktree / ".env")["KEK_PATH"] == str(expected)
PY
# build_verified_npm_ci_command must accept a valid locked package with no
# dependencies; npm ci succeeds without creating node_modules in that case.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "empty-npm-package-fixture"
fixture.mkdir()
fixture.joinpath("package.json").write_text('{"name":"empty","version":"1.0.0"}\n')
fixture.joinpath("package-lock.json").write_text(
    '{"name":"empty","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"empty","version":"1.0.0"}}}\n'
)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_verified_npm_ci_command()],
    cwd=fixture,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stderr
PY

# GuardGuide preview env setup must write APP_URL for the normalized preview
# workspace host, not the physical worktree directory basename.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "guardguide-env-setup-fixture"
worktree_path = fixture / "clones" / "gg123456" / "Steady Otter"
worktree_path.mkdir(parents=True)
worktree_path.joinpath(".env").write_text("APP_URL=https://guardguide.secpal.dev\n")

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_guardguide_preview_env_setup_command()],
    cwd=worktree_path,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stderr
env_text = worktree_path.joinpath(".env").read_text()
assert "APP_URL=https://guardguide-steady-otter.preview.secpal.dev" in env_text, env_text
assert "APP_URL=https://guardguide-Steady Otter.preview.secpal.dev" not in env_text, env_text
PY

# build_verified_npm_ci_command must retry failed npm ci attempts even though
# provisioning runs the generated shell under `set -euo pipefail`.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "npm-ci-retry-fixture"
fake_bin = fixture / "fake-bin"
fixture.mkdir()
fake_bin.mkdir()
fixture.joinpath("package.json").write_text('{"name":"retry","version":"1.0.0","dependencies":{"left-pad":"1.3.0"}}\n')
fixture.joinpath("package-lock.json").write_text(
    '{"name":"retry","version":"1.0.0","lockfileVersion":3,"packages":{"":{"name":"retry","version":"1.0.0"},"node_modules/left-pad":{"version":"1.3.0"}}}\n'
)
fake_bin.joinpath("npm").write_text(
    """#!/usr/bin/env python3
from pathlib import Path
import sys

counter_path = Path("npm-ci-attempts.txt")
attempt = int(counter_path.read_text()) + 1 if counter_path.exists() else 1
counter_path.write_text(str(attempt))
if attempt == 1:
    sys.exit(42)
Path("node_modules").mkdir(exist_ok=True)
Path("node_modules/.package-lock.json").write_text("{}\\n")
sys.exit(0)
"""
)
fake_bin.joinpath("npm").chmod(0o755)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

env = os.environ.copy()
env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
result = subprocess.run(
    ["bash", "-c", "set -euo pipefail; " + module.build_verified_npm_ci_command()],
    cwd=fixture,
    env=env,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stderr
assert fixture.joinpath("npm-ci-attempts.txt").read_text() == "2"
PY

# --prepare-api-worktree CLI path: assert --db-path is threaded into ensure_api_worktree_ready
# Reset api worktree .env so we can re-run via the CLI entry point.
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import subprocess
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "linked-preview-fixture"
db_path = fixture / "polyscope.db"
api_worktree = fixture / "clones" / "api12345" / "azure-cheetah-165552b7"
source_api = fixture / "source-api"

# Reset .env so ensure_api_worktree_ready will update it again
api_worktree.joinpath(".env").write_text(source_api.joinpath(".env").read_text())

env = os.environ.copy()
env["POLYSCOPE_DB_PATH"] = str(db_path)
result = subprocess.run(
    [
        sys.executable,
        str(script_path),
        "--prepare-api-worktree", str(api_worktree),
        "--source-repo-path", str(source_api),
    ],
    env=env,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stderr
api_env = api_worktree.joinpath(".env").read_text()
assert "FRONTEND_URL=https://frontend-azure-cheetah.preview.secpal.dev" in api_env, (
    "CLI --prepare-api-worktree must use POLYSCOPE_DB_PATH to resolve the linked frontend workspace\n" + api_env
)
PY

grep -qF '"command": "npm run validate && npm run lint && npm run format:check"' "$workspace_root/contracts/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/contracts/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/contracts/polyscope.local.json"
grep -qF '"command": "npm run lint && npm run typecheck && npm run test:run && npm run native:verify"' "$workspace_root/android/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/android/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/android/polyscope.local.json"
grep -q '^sdk\.dir=' "$workspace_root/android/android/local.properties"
grep -qF '"command": "npm run check && npm run lint && npm run test && npm run build"' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF '"label": "Build Watch"' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF 'Watching secpal.app preview sources for changes...' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF 'public/og-default.svg' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF 'public/og-de.png' "$workspace_root/secpal.app/polyscope.local.json"
grep -qF '"command": "npm run check && npm run lint && npm run test && npm run build"' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF '"label": "Build Watch"' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF 'Watching guardguide.de preview sources for changes...' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF 'public/og-default.svg' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF 'public/og-de.png' "$workspace_root/guardguide.de/polyscope.local.json"
grep -qF '"command": "npm run check && npm run lint && npm run csp:check && npm run build"' "$workspace_root/changelog/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/changelog/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/changelog/polyscope.local.json"
grep -qF '"label": "Build Watch"' "$workspace_root/changelog/polyscope.local.json"
grep -qF 'Watching changelog preview sources for changes...' "$workspace_root/changelog/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/.github/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/.github/polyscope.local.json"

python3 -B - <<'PY' "$PYTHON_SCRIPT"
import importlib.util
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace = Path(tempfile.mkdtemp(prefix="polyscope-build-watch-"))

try:
    (workspace / "src").mkdir()
    (workspace / "src" / "input.ts").write_text("seed\n")
    (workspace / "package.json").write_text("{}\n")

    command = module.build_preview_full_rebuild_watch_command(
        label="watching",
        watch_directories=["src", "public"],
        ignored_directories=["public/build"],
        watch_files=["package.json"],
        watch_suffixes=[".json", ".ts"],
        build_args=[
            "python3",
            "-c",
            (
                "from pathlib import Path; "
                "counter = Path('build-count.txt'); "
                "count = int(counter.read_text()) + 1 if counter.exists() else 1; "
                "counter.write_text(str(count)); "
                "Path('public/build').mkdir(parents=True, exist_ok=True); "
                "Path('public/build/manifest.json').write_text(str(count))"
            ),
        ],
    )

    process = subprocess.Popen(
        shlex.split(command),
        cwd=workspace,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(3.5)
    process.terminate()

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)

    build_count = int((workspace / "build-count.txt").read_text())
    if build_count != 1:
        raise SystemExit(
            f"build watcher must ignore generated output directories after they appear; observed {build_count} builds"
        )
finally:
    shutil.rmtree(workspace)
PY

python3 -B - <<'PY' "$PYTHON_SCRIPT"
import importlib.util
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

workspace = Path(tempfile.mkdtemp(prefix="polyscope-build-watch-generated-files-"))

try:
    (workspace / "public").mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "input.ts").write_text("seed\n")
    (workspace / "package.json").write_text("{}\n")

    command = module.build_preview_full_rebuild_watch_command(
        label="watching",
        watch_directories=["public", "src"],
        ignored_paths=["public/generated.svg", "public/generated.png"],
        watch_files=["package.json"],
        watch_suffixes=[".json", ".png", ".svg", ".ts"],
        build_args=[
            "python3",
            "-c",
            (
                "from pathlib import Path; "
                "counter = Path('build-count.txt'); "
                "count = int(counter.read_text()) + 1 if counter.exists() else 1; "
                "counter.write_text(str(count)); "
                "Path('public/generated.svg').write_text(f'svg-{count}'); "
                "Path('public/generated.png').write_text(f'png-{count}')"
            ),
        ],
    )

    process = subprocess.Popen(
        shlex.split(command),
        cwd=workspace,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(3.5)
    process.terminate()

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)

    build_count = int((workspace / "build-count.txt").read_text())
    if build_count != 1:
        raise SystemExit(
            f"build watcher must ignore generated files inside watched source trees; observed {build_count} builds"
        )
finally:
    shutil.rmtree(workspace)
PY

python3 -B - <<'PY' "$PYTHON_SCRIPT"
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

command = module.build_static_preview_build_watch_command(
    "changelog",
    ["public", "src"],
    ignored_paths=["public/generated.svg"],
)

for required_suffix in (".avif", ".gif", ".ico", ".jpeg", ".jpg", ".woff2"):
    if required_suffix not in command:
        raise SystemExit(
            f"static preview build watcher must track {required_suffix} assets so preview output stays current"
        )

if "public/generated.svg" not in command:
    raise SystemExit(
        "static preview build watcher must support explicitly ignored generated files"
    )
PY

python3 -B - <<'PY' "$PYTHON_SCRIPT"
import importlib.util
import sys
from pathlib import Path

script_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

command = module.build_guardguide_preview_build_watch_command()

for required_input in ("tailwind.config.js", "tailwind.config.ts", ".png", ".jpg", ".webp", ".woff2"):
    if required_input not in command:
        raise SystemExit(
            f"GuardGuide preview build watcher must track {required_input} changes so preview output stays current"
        )
PY

grep -q 'GuardGuide/AGENTS.md before taking action' "$workspace_root/GuardGuide/polyscope.local.json"
if grep -q 'POLYSCOPE_WORKSPACE=.*python3 -c' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide preview env setup must resolve the normalized workspace directly and not pass the physical basename via POLYSCOPE_WORKSPACE" >&2
    exit 1
fi
grep -q 'APP_URL=https://guardguide-{workspace}\.preview\.secpal\.dev' "$workspace_root/GuardGuide/polyscope.local.json"
grep -q 'php artisan db:seed --class=Database.*GuardGuideAccessSeeder --force && php artisan tinker --execute=' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF "firstOrNew" "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF "test@example.com" "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"command": "npm run format:check && npm run lint:check && npm run typecheck && npm run test && composer run lint:check && composer run analyse && composer run test"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"command": "./scripts/preflight.sh"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"label": "Fix current findings"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"label": "Typecheck"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"command": "npm run typecheck"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"label": "Build"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"command": "npm run build"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF '"label": "Build Watch"' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF 'Watching GuardGuide preview sources for changes...' "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF "public/build" "$workspace_root/GuardGuide/polyscope.local.json"
grep -qF "def is_ignored(path: Path) -> bool:" "$workspace_root/GuardGuide/polyscope.local.json"

if grep -qF '"label": "Vite Dev"' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not start the Vite dev server for nginx-backed previews" >&2
    exit 1
fi

if grep -qF '"command": "npm run dev"' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not run npm dev for nginx-backed previews" >&2
    exit 1
fi

if grep -q 'react-catalyst.instructions.md' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not reference the legacy Catalyst instruction path" >&2
    exit 1
fi

if grep -q 'Catalyst' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not reference Catalyst wording after the shadcn reset" >&2
    exit 1
fi

if grep -qF '"command": "npm run start"' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not reference the removed npm run start command" >&2
    exit 1
fi

if grep -qF '"command": "npm run test:watch"' "$workspace_root/GuardGuide/polyscope.local.json"; then
    echo "GuardGuide Polyscope config must not reference the removed npm run test:watch command" >&2
    exit 1
fi

if grep -q 'node_modules' "$workspace_root/api/polyscope.local.json"; then
    echo "api polyscope config must not reference node_modules" >&2
    exit 1
fi

grep -q 'server_name ~^(?:(?<repo>api|frontend|guardguide-de|guardguide|secpal-app|changelog)-)?(?<workspace>' "$nginx_output"
grep -qF "listen 443 ssl;" "$nginx_output"
grep -qF "listen [::]:443 ssl;" "$nginx_output"
grep -qF "http2 on;" "$nginx_output"
if grep -qF '[0-9a-f]{{8}}' "$nginx_output"; then
    echo "preview nginx config must not reject legitimate branch slugs ending in eight hex characters" >&2
    exit 1
fi
if grep -qF "listen 443 ssl http2;" "$nginx_output" || grep -qF "listen [::]:443 ssl http2;" "$nginx_output"; then
    echo "preview nginx config must not use deprecated listen-level http2 syntax" >&2
    exit 1
fi
if grep -qF "ssi_types text/html;" "$nginx_output"; then
    echo "preview nginx config must not redundantly restate the default text/html SSI type" >&2
    exit 1
fi
python3 -B - <<'PY' "$PYTHON_SCRIPT" "$repos_json" "$workspace/preview-legacy-nginx.conf"
import importlib.util
import json
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
repos_json = pathlib.Path(sys.argv[2])
legacy_output = pathlib.Path(sys.argv[3])

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

assert module.parse_nginx_version("nginx version: nginx/1.24.0") == (1, 24, 0)
assert module.parse_nginx_version("nginx version: nginx/1.25.1") == (1, 25, 1)
assert module.parse_nginx_version("nginx version: nginx/1.27.4 (Ubuntu)") == (1, 27, 4)
assert module.select_nginx_http2_syntax((1, 24, 0)) == "legacy"
assert module.select_nginx_http2_syntax((1, 25, 0)) == "legacy"
assert module.select_nginx_http2_syntax((1, 25, 1)) == "modern"

repo_state = json.loads(repos_json.read_text())
legacy_config = module.render_nginx_config(repo_state, nginx_http2_syntax="legacy")
legacy_output.write_text(legacy_config)

if "listen 443 ssl http2;" not in legacy_config:
    raise SystemExit("legacy nginx render must preserve listen-level http2 for nginx 1.24")
if "listen [::]:443 ssl http2;" not in legacy_config:
    raise SystemExit("legacy nginx render must preserve IPv6 listen-level http2 for nginx 1.24")
if "http2 on;" in legacy_config:
    raise SystemExit("legacy nginx render must not emit the nginx >= 1.25.1 http2 directive")
if "ssi_types text/html;" in legacy_config:
    raise SystemExit("legacy nginx render must not restate the default text/html SSI type")

try:
    module.render_nginx_config(repo_state, nginx_http2_syntax="invalid")
except ValueError:
    pass
else:
    raise SystemExit("unsupported nginx HTTP/2 syntax must fail before rendering")
PY

python3 -B - <<'PY' "$PYTHON_SCRIPT" "$workspace"
import importlib.util
import os
import pathlib
import sys

script_path = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
fixture = workspace / "nginx-helper-dispatch-fixture"
fixture.mkdir()
manifest = fixture / "nginx-manifest.json"
manifest.write_text("{}\n")
fake_sudo = fixture / "sudo"
fake_helper = fixture / "secpal-polyscope-nginx-apply"
command_log = fixture / "commands.log"

fake_sudo.write_text(
    "#!/usr/bin/env bash\n"
    "[[ \"${1:-}\" == '-n' ]] || exit 97\n"
    "shift\n"
    "exec \"$@\"\n"
)
fake_helper.write_text(
    "#!/usr/bin/env bash\n"
    f"printf '%s\\n' \"$*\" >> {command_log!s}\n"
)
for executable in (fake_sudo, fake_helper):
    executable.chmod(0o755)

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
module.DEFAULT_NGINX_MANIFEST_PATH = manifest

module.install_nginx_config(
    manifest,
    sudo_bin=str(fake_sudo),
    helper_path=fake_helper,
)
assert command_log.read_text().splitlines() == [""], command_log.read_text()

alternate_manifest = fixture / "alternate.json"
alternate_manifest.write_text("{}\n")
try:
    module.install_nginx_config(
        alternate_manifest,
        sudo_bin=str(fake_sudo),
        helper_path=fake_helper,
    )
except RuntimeError as error:
    assert "fixed manifest path" in str(error), error
    pass
else:
    raise AssertionError("alternate manifest path reached the privileged helper")

# Root execution must not depend on a sudo binary being installed.
original_geteuid = module.os.geteuid
module.os.geteuid = lambda: 0
try:
    module.install_nginx_config(
        manifest,
        sudo_bin=str(fixture / "missing-sudo"),
        helper_path=fake_helper,
    )
finally:
    module.os.geteuid = original_geteuid

assert command_log.read_text().splitlines() == ["", ""], command_log.read_text()
PY

grep -q "/home/secpal/.polyscope/clones/api12345/\\\$workspace" "$nginx_output"
grep -q "/home/secpal/.polyscope/clones/gg123456/\\\$workspace" "$nginx_output"
grep -qF "if (\$repo = guardguide) {" "$nginx_output"
grep -qF "set \$php_root \$api_public;" "$nginx_output"
grep -qF "set \$php_root \$guardguide_public;" "$nginx_output"
grep -qF "try_files \$uri @preview_router;" "$nginx_output"
grep -qF "try_files \$uri/index.html /index.html =404;" "$nginx_output"
grep -qF "set \$preview_docroot /home/secpal/.polyscope/__missing_preview_docroot__;" "$nginx_output"
grep -qF "set \$preview_relaxed_csp " "$nginx_output"
grep -qF "script-src 'self' 'unsafe-inline'; script-src-attr 'none'; style-src 'self' 'unsafe-inline'; style-src-elem 'self' 'unsafe-inline';" "$nginx_output"
grep -qF "set \$secpal_csp \$preview_relaxed_csp;" "$nginx_output"
if grep -qF "preview_frontend_csp" "$nginx_output" || grep -qF "csp_nonce" "$nginx_output" || grep -qF "nonce-\$csp_nonce" "$nginx_output"; then
    echo "preview nginx config must not advertise nonce-based frontend CSP after SSI removal" >&2
    exit 1
fi
if grep -qF "preview_uses_ssi" "$nginx_output"; then
    echo "preview nginx config must not keep the obsolete preview_uses_ssi toggle" >&2
    exit 1
fi
grep -qF "set \$secpal_permissions_policy " "$nginx_output"
grep -qF "if (!-f \$php_root/index.php) {" "$nginx_output"
grep -qF "fastcgi_pass unix:/run/php/php8.4-fpm-secpal-preview.sock;" "$nginx_output"
grep -qF "fastcgi_buffer_size 32k;" "$nginx_output"
grep -qF "fastcgi_buffers 16 16k;" "$nginx_output"
grep -qF "fastcgi_param SCRIPT_FILENAME \$php_root/index.php;" "$nginx_output"
grep -qF "fastcgi_param DOCUMENT_ROOT \$php_root;" "$nginx_output"
grep -qF "location = / {" "$nginx_output"
grep -qF 'add_header Cache-Control "no-cache, no-store, must-revalidate" always;' "$nginx_output"
grep -qF "location = /sw.js {" "$nginx_output"
grep -qF 'add_header Service-Worker-Allowed "/" always;' "$nginx_output"
grep -qF "location = /manifest.webmanifest {" "$nginx_output"
grep -qF "default_type application/manifest+json;" "$nginx_output"
grep -qF "location ^~ /assets/ {" "$nginx_output"
grep -qF "location ^~ /_astro/ {" "$nginx_output"
grep -qF "location ^~ /_next/static/ {" "$nginx_output"
extract_nginx_block() {
    awk -v start="$1" '
        index($0, start) { in_block=1 }
        in_block {
            print
            opens = gsub(/\{/, "{")
            closes = gsub(/\}/, "}")
            depth += opens - closes
            if (depth <= 0) {
                exit
            }
        }
    ' "$2"
}
if grep -qF "ssi on;" "$nginx_output"; then
    echo "preview nginx config must not enable SSI for workspace-controlled preview HTML" >&2
    exit 1
fi
if grep -qF "@preview_index_ssi" "$nginx_output" || grep -qF "@preview_router_ssi" "$nginx_output"; then
    echo "preview nginx config must not route preview HTML through SSI named locations" >&2
    exit 1
fi
for _shared_loc in "location = / {" "location = /index.html {" "location @preview_router {"; do
    _shared_block="$(extract_nginx_block "$_shared_loc" "$nginx_output")"
    if printf '%s\n' "$_shared_block" | grep -qF "error_page 418" || printf '%s\n' "$_shared_block" | grep -qF "error_page 419"; then
        echo "nginx ${_shared_loc} must not remap requests into SSI handoff locations" >&2
        exit 1
    fi
done
unset -f extract_nginx_block
unset _shared_loc _shared_block
# Immutable-asset location blocks must carry the full security header set; nginx add_header
# inheritance is blocked whenever a location defines its own add_header directives, so each
# block must repeat every header explicitly rather than relying on the parent server block.
for _immutable_loc in "/assets/" "/_astro/" "/_next/static/"; do
    _immutable_block=$(awk "/location \^\~ ${_immutable_loc//\//\\/} \{/,/^[[:space:]]*\}/" "$nginx_output")
    if printf '%s\n' "$_immutable_block" | tail -n +2 | grep -qE '^[[:space:]]*location '; then
        echo "nginx location ^~ ${_immutable_loc} block parser captured a following location" >&2
        exit 1
    fi
    for _immutable_header in \
        'add_header Content-Security-Policy' \
        'add_header Permissions-Policy' \
        'add_header Strict-Transport-Security' \
        'add_header X-Content-Type-Options' \
        'add_header X-Frame-Options' \
        'add_header X-Permitted-Cross-Domain-Policies'; do
        if ! printf '%s\n' "$_immutable_block" | grep -qF "$_immutable_header"; then
            echo "nginx location ^~ ${_immutable_loc} is missing: ${_immutable_header}" >&2
            exit 1
        fi
    done
    _cache_header='add_header Cache-Control "public, immutable"'
    [ "$_immutable_loc" = "/assets/" ] && _cache_header='add_header Cache-Control "no-cache, must-revalidate"'
    if ! printf '%s\n' "$_immutable_block" | grep -qF "$_cache_header"; then
        echo "nginx location ^~ ${_immutable_loc} is missing: ${_cache_header}" >&2
        exit 1
    fi
    if ! printf '%s\n' "$_immutable_block" | grep -qF "if (\$uri ~ (?:/\\.|\\.php$)) {"; then
        echo "nginx location ^~ ${_immutable_loc} must deny nested hidden files and PHP files" >&2
        exit 1
    fi
done
unset _immutable_loc _immutable_block _immutable_header

if grep -qF "fastcgi_pass unix:/run/php/php8.4-fpm-secpal-api.sock;" "$nginx_output"; then
    echo "preview nginx config must not route shared preview PHP traffic through the API-specific FPM pool" >&2
    exit 1
fi

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
guardguide_de_if_line="$(grep -nF "if (-f \$guardguide_de_dist/index.html) {" "$nginx_output" | head -n 1 | cut -d: -f1)"
changelog_if_line="$(grep -nF "if (-f \$changelog_out/index.html) {" "$nginx_output" | head -n 1 | cut -d: -f1)"

test -n "$api_if_line"
test -n "$frontend_if_line"
test -n "$secpal_app_if_line"
test -n "$guardguide_de_if_line"
test -n "$changelog_if_line"

if (( api_if_line >= frontend_if_line || frontend_if_line >= secpal_app_if_line || secpal_app_if_line >= guardguide_de_if_line || guardguide_de_if_line >= changelog_if_line )); then
    echo "generic preview precedence must prefer changelog > guardguide.de > secpal.app > frontend > api" >&2
    exit 1
fi

"$PRETTIER_BIN" --check \
    "$workspace_root/api/polyscope.local.json" \
    "$workspace_root/frontend/polyscope.local.json" \
    "$workspace_root/contracts/polyscope.local.json" \
    "$workspace_root/android/polyscope.local.json" \
    "$workspace_root/GuardGuide/polyscope.local.json" \
    "$workspace_root/secpal.app/polyscope.local.json" \
    "$workspace_root/guardguide.de/polyscope.local.json" \
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
org_prompts = cur.execute(
    'select review_prompt, merge_prompt, merge_and_push_prompt from repositories where id = ?',
    ('gh123456',),
).fetchone()
prompt_rows = cur.execute(
    'select review_prompt, pr_prompt, draft_pr_prompt, merge_prompt, merge_and_push_prompt from repositories order by id'
).fetchall()
links = cur.execute('select repo_id, linked_repo_id from repository_links order by repo_id, linked_repo_id').fetchall()

assert 'api/AGENTS.md' in api_prompt
assert 'Do not add AI agent attribution' in api_prompt
assert 'generated-by text' in frontend_prompt
assert 'tool-specific labels or prefixes' in frontend_prompt
assert 'Run git status --short --branch before any write action.' in api_prompt
assert 'Use Form Requests for validation and services for business logic.' in api_prompt
assert 'Keep changes repo-local, minimal, and consistent with the repository stack.' in api_prompt
assert 'Write a concise English PR body for SecPal/frontend.' in frontend_prompt
assert 'Preserve a branch or worktree already supplied by the execution environment.' in org_prompts[0]
assert 'Run the smallest relevant validation while iterating' in org_prompts[1]
for row in prompt_rows:
    for prompt in row:
        assert 'Do not add AI agent attribution' in prompt
        assert 'generated-by text' in prompt
        assert 'tool-specific labels or prefixes' in prompt
        assert 'pull the relevant linked workspaces' not in prompt
        assert 'after merge return the repo to the ready state' not in prompt
        assert 'Preserve this repository-owned review profile.' not in prompt
        assert 'LEGACY RUNTIME MARKER' not in prompt
        assert 'LEGACY VALIDATION MARKER' not in prompt
        assert 'LEGACY TRIAGE MARKER' not in prompt
        assert 'LEGACY TRACKING MARKER' not in prompt
assert ('api12345', 'an123456') in links
assert ('api12345', 'co123456') in links
assert ('api12345', 'fe123456') in links
assert ('gg123456', 'an123456') in links
assert ('gg123456', 'api12345') in links
assert ('gg123456', 'co123456') in links
assert ('gg123456', 'fe123456') in links
assert ('sa123456', 'ch123456') in links

summary = json.loads(summary_path.read_text())
assert summary['db_backup'] is not None
assert summary['repositories']['api']['preview_prefix'] == 'api'
assert summary['repositories']['frontend']['preview_prefix'] == 'frontend'
assert summary['repositories']['GuardGuide']['preview_prefix'] == 'guardguide'
assert summary['repositories']['secpal.app']['preview_prefix'] == 'secpal-app'
assert summary['repositories']['guardguide.de']['preview_prefix'] == 'guardguide-de'
assert summary['repositories']['changelog']['preview_prefix'] == 'changelog'
assert summary['repositories']['contracts']['preview_prefix'] is None
assert summary['repositories']['api']['agent_instructions'].endswith('/api/AGENTS.md')
assert summary['repositories']['api']['focus_instruction_paths'][0].endswith('org-shared.instructions.md')
assert summary['repositories']['GuardGuide']['focus_instruction_paths'][1].endswith('php-laravel.instructions.md')
assert summary['repositories']['.github']['linked_repositories'] == []
assert summary['repositories']['GuardGuide']['linked_repositories'] == ['api', 'frontend', 'contracts', 'android']
PY

python3 -B - <<'PY' "$workspace_root"
import json
import sys
from pathlib import Path

workspace_root = Path(sys.argv[1])
config_paths = sorted(workspace_root.glob("*/polyscope.local.json"))
config_paths.append(workspace_root / ".github" / "polyscope.local.json")
for config_path in config_paths:
    payload = json.loads(config_path.read_text())
    for task in payload.get("tasks", []):
        prompt = task.get("prompt", "")
        assert "Do not add AI agent attribution" in prompt, (config_path, task.get("label"), prompt)
        assert "generated-by text" in prompt, (config_path, task.get("label"), prompt)
        assert "tool-specific labels or prefixes" in prompt, (config_path, task.get("label"), prompt)
PY

initial_db_hash="$(file_sha256 "$db_path")"
initial_backup_count="$(find "$workspace" -maxdepth 1 -name 'polyscope.db.backup-*' | wc -l)"
initial_guardguide_copilot_hash="$(file_sha256 "$workspace_root/GuardGuide/.github/copilot-instructions.md")"

python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$repeat_summary_output" \
    > /dev/null

repeat_db_hash="$(file_sha256 "$db_path")"
repeat_backup_count="$(find "$workspace" -maxdepth 1 -name 'polyscope.db.backup-*' | wc -l)"
repeat_guardguide_copilot_hash="$(file_sha256 "$workspace_root/GuardGuide/.github/copilot-instructions.md")"

if [ "$repeat_backup_count" -ne "$initial_backup_count" ]; then
    echo "repeat metadata sync must not create another DB backup when repository metadata is unchanged" >&2
    exit 1
fi

if [ "$repeat_db_hash" != "$initial_db_hash" ]; then
    echo "repeat metadata sync must leave polyscope.db unchanged when repository metadata is already up to date" >&2
    exit 1
fi

if [ "$repeat_guardguide_copilot_hash" != "$initial_guardguide_copilot_hash" ]; then
    echo "repeat metadata sync must preserve independent Copilot profiles" >&2
    exit 1
fi

python3 - <<'PY' "$repeat_summary_output"
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text())
assert summary['db_backup'] is None
PY

provision_log="$workspace/provision.log"
fake_psql_log="$workspace/psql.log"
fake_pg_state="$workspace/postgres-state.json"
fake_exec_dir="$workspace/fake-exec"
service_path="$fake_exec_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
api_clone="$home_dir/.polyscope/clones/api12345/auto-hawk"
broken_api_clone="$home_dir/.polyscope/clones/api12345/fix"
garbled_git_api_clone="$home_dir/.polyscope/clones/api12345/chore"
frontend_clone="$home_dir/.polyscope/clones/fe123456/auto-hawk"
broken_frontend_clone="$home_dir/.polyscope/clones/fe123456/feat"
broken_android_clone="$home_dir/.polyscope/clones/an123456/feat"
android_clone="$home_dir/.polyscope/clones/an123456/auto-hawk"
mkdir -p "$fake_exec_dir" "$api_clone/.git/info" "$api_clone/.git/hooks" "$api_clone/scripts" "$broken_api_clone/.git" "$garbled_git_api_clone" "$frontend_clone/.git/info" "$frontend_clone/.git/hooks" "$frontend_clone/scripts" "$broken_frontend_clone" "$broken_android_clone/.git/info" "$broken_android_clone/.git/hooks" "$android_clone/.git/info" "$android_clone/.git/hooks"
printf 'not-a-git-pointer\n' > "$garbled_git_api_clone/.git"
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
if [[ -n "${FAIL_ON_WORKTREE:-}" && "$PWD" == "$FAIL_ON_WORKTREE" ]]; then
    exit 23
fi
exit 0
STUB
chmod +x "$fake_exec_dir/php"

cat >"$fake_exec_dir/npm" <<'STUB'
#!/usr/bin/env bash
printf 'npm:%s:%s\n' "$PWD" "$*" >> "$PROVISION_LOG"
if [[ "$*" == *" ci"* || "$1" == "ci" ]]; then
    mkdir -p node_modules/typescript/lib node_modules/@types/node
    printf '{}\n' > node_modules/.package-lock.json
    printf '// fake lib\n' > node_modules/typescript/lib/lib.es2020.d.ts
    printf '// fake lib\n' > node_modules/typescript/lib/lib.dom.d.ts
    printf '{ "name": "@types/node" }\n' > node_modules/@types/node/package.json
fi
if [[ "$*" == *"run build"* ]]; then
    out_dir="dist"
    prev=""
    for arg in "$@"; do
        if [[ "$prev" == "--outDir" ]]; then
            out_dir="$arg"
            break
        fi
        prev="$arg"
    done
    mkdir -p "$out_dir/assets" "$out_dir/.well-known"
    printf '<!doctype html>\n' > "$out_dir/index.html"
    printf 'self.skipWaiting();\n' > "$out_dir/sw.js"
    printf '{}\n' > "$out_dir/manifest.webmanifest"
    printf 'console.log("chunk");\n' > "$out_dir/assets/index-abc123.js"
    printf '{}\n' > "$out_dir/.well-known/assetlinks.json"
fi
exit 0
STUB
chmod +x "$fake_exec_dir/npm"

cat >"$fake_exec_dir/psql" <<'STUB'
#!/usr/bin/env python3
import json
import os
import re
import shlex
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
    handle.write(f"psql:{os.getcwd()}:{shlex.join(args)}:{sql}\n")

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

seed_api_worktree_files "$api_clone"
write_valid_worktree_instructions "$broken_api_clone"
seed_node_worktree_files "$frontend_clone" "frontend-auto-hawk"
seed_node_worktree_files "$broken_android_clone" "android-feat"
seed_node_worktree_files "$android_clone" "android-auto-hawk"
mkdir -p "$android_clone/android"
touch "$android_clone/android/settings.gradle"
cat >"$android_clone/android/local.properties" <<'EOF'
ndk.dir=/opt/android-ndk
sdk.dir=/tmp/obsolete-sdk
cmake.dir=/opt/android-cmake
EOF

cp "$workspace_root/api/.env" "$api_clone/.env"
: > "$broken_api_clone/.env"

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

cat >"$frontend_clone/.env.preview.local" <<'EOF'
VITE_API_URL=https://api.secpal.dev
EOF

cat >"$frontend_clone/.env.production.local" <<'EOF'
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

shared_android_sdk_root="$workspace/shared-android-sdk"
mkdir -p "$shared_android_sdk_root/platform-tools" "$shared_android_sdk_root/cmdline-tools/latest"

# Canonical validation of all candidate worktrees must finish before the first
# worktree-local configuration, setup, alias, hook, or provision-marker write.
assert_invalid_candidate_blocks_provisioning() {
    local fixture_name="$1"
    local target_file="$2"
    local fixture_mode="$3"
    local expected_reason="$4"
    local invalid_instruction_clone="$home_dir/.polyscope/clones/fe123456/$fixture_name"
    local invalid_candidate_summary="$workspace/$fixture_name-summary.json"
    local invalid_candidate_stdout="$workspace/$fixture_name.stdout"
    local invalid_candidate_stderr="$workspace/$fixture_name.stderr"
    local api_env_hash_before_invalid_candidate
    local db_hash_before_invalid_candidate
    local pg_state_hash_before_invalid_candidate

    mkdir -p "$invalid_instruction_clone/.git/info"
    seed_node_worktree_files "$invalid_instruction_clone" "frontend-$fixture_name"
    case "$fixture_mode" in
        duplicate-heading)
            printf '\n# Duplicate Top-Level Heading\n' \
                >>"$invalid_instruction_clone/$target_file"
            ;;
        missing-spdx)
            sed -i '/SPDX-License''-Identifier:/d' \
                "$invalid_instruction_clone/$target_file"
            ;;
        *)
            echo "unsupported invalid candidate fixture: $fixture_mode" >&2
            exit 1
            ;;
    esac

    replace_registered_worktrees "fe123456" "$invalid_instruction_clone"
    api_env_hash_before_invalid_candidate="$(file_sha256 "$api_clone/.env")"
    db_hash_before_invalid_candidate="$(file_sha256 "$db_path")"
    pg_state_hash_before_invalid_candidate="$(file_sha256 "$fake_pg_state")"

    if env HOME="$home_dir" \
            PATH="$service_path" \
            POLYSCOPE_ANDROID_SDK_ROOT="$shared_android_sdk_root" \
            PROVISION_LOG="$provision_log" \
            FAKE_PSQL_LOG="$fake_psql_log" \
            FAKE_PSQL_STATE="$fake_pg_state" \
            python3 "$PYTHON_SCRIPT" \
            --workspace-root "$workspace_root" \
            --db-path "$db_path" \
            --repo-state-file "$repos_json" \
            --nginx-output "$nginx_output" \
            --summary-output "$invalid_candidate_summary" \
            --skip-local-configs \
            --skip-db-sync \
            --provision-worktrees \
            >"$invalid_candidate_stdout" 2>"$invalid_candidate_stderr"; then
        echo "rollout must fail when candidate $fixture_name has invalid instructions" >&2
        exit 1
    fi

    grep -qF "canonical AI-instruction validation failed for $invalid_instruction_clone" \
        "$invalid_candidate_stderr"
    grep -qF "$(basename "$target_file")" "$invalid_candidate_stderr"
    grep -qF "$expected_reason" "$invalid_candidate_stderr"
    test "$(file_sha256 "$api_clone/.env")" = "$api_env_hash_before_invalid_candidate"
    test "$(file_sha256 "$db_path")" = "$db_hash_before_invalid_candidate"
    test "$(file_sha256 "$fake_pg_state")" = "$pg_state_hash_before_invalid_candidate"
    test ! -s "$provision_log"
    test ! -e "$api_clone/polyscope.local.json"
    test ! -e "$api_clone/.polyscope-secpal-provisioned.json"
    test ! -e "$frontend_clone/polyscope.local.json"
    test ! -e "$frontend_clone/.polyscope-secpal-provisioned.json"
    test ! -e "$invalid_instruction_clone/polyscope.local.json"
    test ! -e "$invalid_instruction_clone/.polyscope-secpal-provisioned.json"
    python3 - "$invalid_candidate_summary" "$invalid_instruction_clone" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text())
invalid_path = sys.argv[2]
assert summary.get("provisioned_worktrees", []) == [], summary
failures = summary.get("failed_provision_worktrees", [])
assert len(failures) == 1, failures
assert failures[0]["path"] == invalid_path, failures
assert "canonical AI-instruction validation failed" in failures[0]["error"], failures
PY
    replace_registered_worktrees
    rm -rf "$invalid_instruction_clone"
}

assert_invalid_candidate_blocks_provisioning \
    "invalid-agents" "AGENTS.md" "duplicate-heading" \
    "instruction Markdown passes lint"
assert_invalid_candidate_blocks_provisioning \
    "invalid-copilot" ".github/copilot-instructions.md" "missing-spdx" \
    "Missing inline SPDX header or .license sidecar"

replace_registered_worktrees \
    "api12345" "$api_clone" \
    "api12345" "$broken_api_clone" \
    "api12345" "$garbled_git_api_clone" \
    "fe123456" "$frontend_clone" \
    "fe123456" "$broken_frontend_clone" \
    "an123456" "$broken_android_clone" \
    "an123456" "$android_clone"

provision_summary_json="$workspace/provision-summary.json"
env HOME="$home_dir" \
    PATH="$service_path" \
    POLYSCOPE_ANDROID_SDK_ROOT="$shared_android_sdk_root" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
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
assert 'android:auto-hawk' in provisioned, f"expected android:auto-hawk in provisioned_worktrees, got {provisioned}"
assert 'api:fix' not in provisioned, f"did not expect api:fix in provisioned_worktrees, got {provisioned}"
assert 'api:chore' not in provisioned, f"did not expect api:chore in provisioned_worktrees, got {provisioned}"
assert 'frontend:feat' not in provisioned, f"did not expect frontend:feat in provisioned_worktrees, got {provisioned}"
assert 'android:feat' not in provisioned, f"did not expect android:feat in provisioned_worktrees, got {provisioned}"
assert cleaned == [], f"expected no cleaned preview databases on first provisioning run, got {cleaned}"
PY

grep -qF 'APP_URL=https://api-auto-hawk.preview.secpal.dev' "$api_clone/.env"
grep -qF 'FRONTEND_URL=https://frontend-auto-hawk.preview.secpal.dev' "$api_clone/.env"
grep -qF 'DB_CONNECTION=pgsql' "$api_clone/.env"
grep -qF 'DB_DATABASE=secpal__preview__auto_hawk' "$api_clone/.env"
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$api_clone/.env"
grep -qF "KEK_PATH=$api_clone/storage/app/keys/kek.key" "$api_clone/.env"
grep -qF 'SANCTUM_STATEFUL_DOMAINS=frontend-auto-hawk.preview.secpal.dev,auto-hawk.preview.secpal.dev,app.secpal.dev' "$api_clone/.env"
grep -qF 'CORS_ALLOWED_ORIGINS=https://frontend-auto-hawk.preview.secpal.dev,https://auto-hawk.preview.secpal.dev,https://app.secpal.dev' "$api_clone/.env"
grep -qF 'VITE_API_URL=https://api-auto-hawk.preview.secpal.dev' "$frontend_clone/.env.local"
grep -qF 'VITE_API_URL=https://api-auto-hawk.preview.secpal.dev' "$frontend_clone/.env.preview.local"
grep -qF 'VITE_API_URL=https://api-auto-hawk.preview.secpal.dev' "$frontend_clone/.env.production.local"
test -f "$api_clone/polyscope.local.json"
test -f "$frontend_clone/polyscope.local.json"
grep -qF 'prepare-api-worktree' "$api_clone/polyscope.local.json"
grep -qF 'source-repo-path' "$api_clone/polyscope.local.json"
grep -qF 'resolve_linked_workspace(\"SecPal/api\", workspace)' "$frontend_clone/polyscope.local.json"
python3 - "$api_clone/.polyscope-secpal-provisioned.json" "$frontend_clone/.polyscope-secpal-provisioned.json" <<'PY'
import json
import sys

for marker_path in sys.argv[1:]:
    marker = json.loads(open(marker_path).read())
    assert marker["workspace"] == "auto-hawk", marker
PY
grep -q '^sdk\.dir='"$shared_android_sdk_root"'$' "$android_clone/android/local.properties"
grep -q '^ndk\.dir=/opt/android-ndk$' "$android_clone/android/local.properties"
grep -q '^cmake\.dir=/opt/android-cmake$' "$android_clone/android/local.properties"
grep -q '^polyscope.local.json$' "$api_clone/.git/info/exclude"
grep -qF '.polyscope-secpal-provisioned.json' "$api_clone/.git/info/exclude"
grep -q '^android/local\.properties$' "$android_clone/.git/info/exclude"
test -x "$api_clone/.git/hooks/pre-commit"
test -L "$api_clone/.git/hooks/pre-push"
test "$(readlink "$api_clone/.git/hooks/pre-push")" = '../../scripts/preflight.sh'
test -L "$api_clone/.git/hooks/commit-msg"
readlink "$api_clone/.git/hooks/commit-msg" | grep -qF 'strip-ai-trailers.sh'
test -x "$frontend_clone/.git/hooks/pre-commit"
test -L "$frontend_clone/.git/hooks/pre-push"
test "$(readlink "$frontend_clone/.git/hooks/pre-push")" = '../../scripts/preflight.sh'
test -L "$frontend_clone/.git/hooks/commit-msg"
readlink "$frontend_clone/.git/hooks/commit-msg" | grep -qF 'strip-ai-trailers.sh'
test -f "$api_clone/.polyscope-secpal-provisioned.json"
test -f "$frontend_clone/.polyscope-secpal-provisioned.json"
test ! -f "$broken_api_clone/polyscope.local.json"
test ! -f "$broken_api_clone/.polyscope-secpal-provisioned.json"
test ! -f "$garbled_git_api_clone/polyscope.local.json"
test ! -f "$garbled_git_api_clone/.polyscope-secpal-provisioned.json"
test ! -f "$broken_frontend_clone/polyscope.local.json"
test ! -f "$broken_frontend_clone/.polyscope-secpal-provisioned.json"
test ! -f "$broken_android_clone/android/local.properties"
test ! -f "$broken_android_clone/.polyscope-secpal-provisioned.json"
grep -qF "composer:$api_clone:install" "$provision_log"
grep -qF "php:$api_clone:artisan config:clear" "$provision_log"
grep -qF "php:$api_clone:artisan migrate --force" "$provision_log"
grep -qF "php:$api_clone:artisan addresses:import --if-empty --setup-only --no-interaction" "$provision_log"
grep -qF "php:$api_clone:artisan db:seed --force" "$provision_log"
grep -qF "php:$api_clone:artisan tinker --execute=" "$provision_log"
grep -qF "npm:$frontend_clone:ci" "$provision_log"
grep -qF "npm:$frontend_clone:run build -- --mode preview" "$provision_log"
grep -qF "pre-commit:$api_clone:install --install-hooks --hook-type pre-commit" "$provision_log"
grep -qF "pre-commit:$frontend_clone:install --install-hooks --hook-type pre-commit" "$provision_log"
grep -qF "SELECT 1 FROM pg_database WHERE datname = 'secpal__preview__auto_hawk'" "$fake_psql_log"
grep -qF 'CREATE DATABASE "secpal__preview__auto_hawk"' "$fake_psql_log"
grep -qF -- '-h 127.0.0.1 -p 5432 -U secpal -d secpal -Atqc' "$fake_psql_log"

if grep -qF "$broken_api_clone" "$provision_log"; then
    echo "provisioning must skip invalid api stub directories" >&2
    exit 1
fi

if grep -qF "$garbled_git_api_clone" "$provision_log"; then
    echo "provisioning must skip api worktrees with garbled .git files" >&2
    exit 1
fi

if grep -qF "$broken_frontend_clone" "$provision_log"; then
    echo "provisioning must skip invalid frontend stub directories" >&2
    exit 1
fi

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert 'secpal' in state['databases']
assert 'secpal__preview__auto_hawk' in state['databases']
PY

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
state['databases'].append('secpal__preview__fix')
open(sys.argv[1], 'w').write(json.dumps(state))
PY

invalid_dir_cleanup_summary_json="$workspace/invalid-dir-cleanup-summary.json"
replace_registered_worktrees \
    "api12345" "$api_clone" \
    "fe123456" "$frontend_clone" \
    "an123456" "$android_clone"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$invalid_dir_cleanup_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$invalid_dir_cleanup_summary_json" "$fake_pg_state" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
state = json.loads(open(sys.argv[2]).read())

assert summary.get('provisioned_worktrees', []) == [], summary.get('provisioned_worktrees', [])
assert summary.get('cleaned_preview_storage_targets', []) == ['secpal__preview__fix'], summary.get('cleaned_preview_storage_targets', [])
assert 'secpal__preview__fix' not in state['databases'], state['databases']
PY

grep -qF 'DROP DATABASE IF EXISTS "secpal__preview__fix" WITH (FORCE)' "$fake_psql_log"

# An active API registration may briefly precede its filesystem materialization.
# Its deterministic preview target remains live until the registration itself
# becomes inactive, regardless of provisioning eligibility.
missing_active_api_clone="$home_dir/.polyscope/clones/api12345/pending-otter"
python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
state['databases'].append('secpal__preview__pending_otter')
open(sys.argv[1], 'w').write(json.dumps(state))
PY

missing_active_summary_json="$workspace/missing-active-summary.json"
replace_registered_worktrees \
    "api12345" "$api_clone" \
    "api12345" "$missing_active_api_clone" \
    "fe123456" "$frontend_clone" \
    "an123456" "$android_clone"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$missing_active_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$missing_active_summary_json" "$fake_pg_state" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
state = json.loads(open(sys.argv[2]).read())
assert summary.get('cleaned_preview_storage_targets', []) == [], summary
assert 'secpal__preview__pending_otter' in state['databases'], state['databases']
PY

missing_removed_summary_json="$workspace/missing-removed-summary.json"
replace_registered_worktrees \
    "api12345" "$api_clone" \
    "fe123456" "$frontend_clone" \
    "an123456" "$android_clone"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$missing_removed_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - "$missing_removed_summary_json" "$fake_pg_state" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
state = json.loads(open(sys.argv[2]).read())
assert summary.get('cleaned_preview_storage_targets', []) == ['secpal__preview__pending_otter'], summary
assert 'secpal__preview__pending_otter' not in state['databases'], state['databases']
PY

legacy_hashed_api_clone="$home_dir/.polyscope/clones/api12345/legacy-hawk-165552b7"
mkdir -p "$legacy_hashed_api_clone/.git/info" "$legacy_hashed_api_clone/.git/hooks" "$legacy_hashed_api_clone/scripts"
seed_api_worktree_files "$legacy_hashed_api_clone"
cat >"$legacy_hashed_api_clone/.env" <<'EOF'
APP_URL=https://api-legacy-hawk.preview.secpal.dev
FRONTEND_URL=https://frontend-legacy-hawk.preview.secpal.dev
DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=secpal__preview__legacy_hawk_165552b7
DB_USERNAME=secpal
DB_PASSWORD=
SESSION_DOMAIN=.secpal.dev
SANCTUM_STATEFUL_DOMAINS=frontend-legacy-hawk.preview.secpal.dev,legacy-hawk.preview.secpal.dev,app.secpal.dev
CORS_ALLOWED_ORIGINS=https://frontend-legacy-hawk.preview.secpal.dev,https://legacy-hawk.preview.secpal.dev,https://app.secpal.dev
EOF
cat >"$legacy_hashed_api_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF
cat >"$legacy_hashed_api_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$legacy_hashed_api_clone/scripts/preflight.sh"

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
state['databases'].append('secpal__preview__legacy_hawk_165552b7')
open(sys.argv[1], 'w').write(json.dumps(state))
PY

stale_api_clone="$home_dir/.polyscope/clones/api12345/stale-otter"
mkdir -p "$stale_api_clone/.git/info" "$stale_api_clone/.git/hooks" "$stale_api_clone/scripts"
seed_api_worktree_files "$stale_api_clone"
cp "$workspace_root/api/.env" "$stale_api_clone/.env"

cat >"$stale_api_clone/.pre-commit-config.yaml" <<'EOF'
repos: []
EOF

cat >"$stale_api_clone/scripts/preflight.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$stale_api_clone/scripts/preflight.sh"

stale_provision_summary_json="$workspace/stale-provision-summary.json"
replace_registered_worktrees \
    "api12345" "$api_clone" \
    "fe123456" "$frontend_clone" \
    "an123456" "$android_clone" \
    "api12345" "$legacy_hashed_api_clone" \
    "api12345" "$stale_api_clone"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
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
assert 'api:legacy-hawk' in provisioned, f"expected legacy hashed api worktree to reprovision as api:legacy-hawk, got {provisioned}"
assert cleaned == [], f"expected no cleaned preview databases while stale-otter still exists, got {cleaned}"
PY

grep -qF 'APP_URL=https://api-stale-otter.preview.secpal.dev' "$stale_api_clone/.env"
grep -qF 'FRONTEND_URL=https://frontend-stale-otter.preview.secpal.dev' "$stale_api_clone/.env"
grep -qF 'DB_DATABASE=secpal__preview__stale_otter' "$stale_api_clone/.env"
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$stale_api_clone/.env"
grep -qxF 'DB_DATABASE=secpal__preview__legacy_hawk' "$legacy_hashed_api_clone/.env"
if grep -qF 'DB_DATABASE=secpal__preview__legacy_hawk_165552b7__preview__legacy_hawk' "$legacy_hashed_api_clone/.env"; then
    echo "legacy hashed preview database migration must not derive a nested preview database name" >&2
    exit 1
fi
grep -qF 'POLYSCOPE_BASE_DB_DATABASE=secpal' "$legacy_hashed_api_clone/.env"
test -f "$stale_api_clone/.polyscope-secpal-provisioned.json"
grep -qF 'CREATE DATABASE "secpal__preview__stale_otter"' "$fake_psql_log"

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert 'secpal__preview__stale_otter' in state['databases']
assert 'secpal__preview__legacy_hawk_165552b7' in state['databases']
PY

rm -rf "$stale_api_clone"
rm -rf "$legacy_hashed_api_clone"

# Inject a stale schema alongside the stale database to verify that in database mode
# (rolcreatedb=true) the cleanup also prunes orphaned schemas from a previous schema-mode run.
python3 - "$fake_pg_state" <<'PY'
import json, sys
state = json.loads(open(sys.argv[1]).read())
state.setdefault("schemas", []).append("secpal__preview__legacy_schema_otter")
open(sys.argv[1], "w").write(json.dumps(state))
PY

cleanup_summary_json="$workspace/cleanup-summary.json"
replace_registered_worktrees \
    "api12345" "$api_clone" \
    "fe123456" "$frontend_clone" \
    "an123456" "$android_clone"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
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
assert 'secpal__preview__legacy_hawk_165552b7' in cleaned, f"expected migrated legacy hashed db in cleaned after worktree removal, got {cleaned}"
assert 'secpal__preview__legacy_schema_otter' in cleaned, f"expected stale schema in cleaned even in database mode, got {cleaned}"
assert 'secpal__preview__auto_hawk' in state['databases']
assert 'secpal__preview__stale_otter' not in state['databases']
assert 'secpal__preview__legacy_hawk_165552b7' not in state['databases']
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
    --db-path "$db_path" \
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

failing_api_clone="$home_dir/.polyscope/clones/api12345/abort-hawk"
failing_api_cleanup_clone="$home_dir/.polyscope/clones/api12345/broken-mole"
failing_api_alias_clone="$home_dir/.polyscope/clones/api12345/Steady Otter"
failing_frontend_manifest_clone="$home_dir/.polyscope/clones/fe123456/broken-ibis"
failing_frontend_io_clone="$home_dir/.polyscope/clones/fe123456/locked-oryx"
guardguide_clone="$home_dir/.polyscope/clones/gg123456/steady-otter"
failure_isolation_summary_json="$workspace/failure-isolation-summary.json"
failing_api_alias_workspace="$(python3 - <<'PY'
import hashlib
print("steady-otter-" + hashlib.sha1("Steady Otter".encode("utf-8")).hexdigest()[:8])
PY
)"

mkdir -p "$failing_api_clone/.git/info" "$failing_api_clone/.git/hooks" "$failing_api_clone/scripts"
mkdir -p "$failing_api_cleanup_clone/.git/info" "$failing_api_cleanup_clone/.git/hooks" "$failing_api_cleanup_clone/scripts"
mkdir -p "$failing_api_alias_clone/.git/info" "$failing_api_alias_clone/.git/hooks" "$failing_api_alias_clone/scripts"
mkdir -p "$failing_frontend_manifest_clone/.git/info" "$failing_frontend_manifest_clone/.git/hooks" "$failing_frontend_manifest_clone/scripts"
mkdir -p "$failing_frontend_io_clone/.git/info" "$failing_frontend_io_clone/.git/hooks" "$failing_frontend_io_clone/scripts"
mkdir -p "$guardguide_clone/.git/info" "$guardguide_clone/.git/hooks" "$guardguide_clone/database"

seed_api_worktree_files "$failing_api_clone"
seed_api_worktree_files "$failing_api_cleanup_clone"
seed_api_worktree_files "$failing_api_alias_clone"
seed_node_worktree_files "$failing_frontend_manifest_clone" "frontend-broken-ibis"
seed_node_worktree_files "$failing_frontend_io_clone" "frontend-locked-oryx"
seed_api_worktree_files "$guardguide_clone"
seed_node_worktree_files "$guardguide_clone" "guardguide-steady-otter"
cp "$workspace_root/api/.env" "$failing_api_clone/.env"
mkdir -p "$home_dir/.polyscope/clones/api12345/$failing_api_alias_workspace"
printf '{\n  "packages": []\n}\n' > "$guardguide_clone/composer.lock"
printf '{"scripts": ' > "$failing_api_cleanup_clone/composer.json"
printf '{"scripts": ' > "$failing_frontend_manifest_clone/package.json"
rm -rf "$failing_frontend_io_clone/.git/info"
printf 'not a directory\n' > "$failing_frontend_io_clone/.git/info"
printf 'APP_KEY=\n' > "$guardguide_clone/.env.example"

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
state['databases'].append('secpal__preview__broken_mole')
state.setdefault('schemas', []).append('secpal__preview__broken_mole')
open(sys.argv[1], 'w').write(json.dumps(state))
PY

replace_registered_worktrees \
    "api12345" "$failing_api_clone" \
    "api12345" "$failing_api_cleanup_clone" \
    "api12345" "$failing_api_alias_clone" \
    "fe123456" "$failing_frontend_manifest_clone" \
    "fe123456" "$failing_frontend_io_clone" \
    "gg123456" "$guardguide_clone"

env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    FAIL_ON_WORKTREE="$failing_api_clone" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$failure_isolation_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null || failure_isolation_exit=$?

test "${failure_isolation_exit:-0}" -eq 1

python3 - "$failure_isolation_summary_json" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
failed = summary.get('failed_provision_worktrees', [])
cleaned = summary.get('cleaned_preview_storage_targets', [])

assert 'GuardGuide:steady-otter' in provisioned, provisioned
assert 'api:abort-hawk' not in provisioned, provisioned
assert 'api:broken-mole' not in provisioned, provisioned
assert 'api:steady-otter' not in provisioned, provisioned
assert 'frontend:broken-ibis' not in provisioned, provisioned
assert 'frontend:locked-oryx' not in provisioned, provisioned
assert 'secpal__preview__broken_mole' not in cleaned, cleaned
assert any(
    entry.get('repo') == 'api'
    and entry.get('workspace') == 'abort-hawk'
    and '--bootstrap-api-worktree "$PWD"' in entry.get('error', '')
    for entry in failed
), failed
assert any(
    entry.get('repo') == 'api'
    and entry.get('workspace') == 'broken-mole'
    and 'invalid composer.json for rollout validation' in entry.get('error', '')
    for entry in failed
), failed
assert any(
    entry.get('repo') == 'api'
    and entry.get('workspace') == 'Steady Otter'
    and 'already exists and does not point' in entry.get('error', '')
    for entry in failed
), failed
assert any(
    entry.get('repo') == 'frontend'
    and entry.get('workspace') == 'broken-ibis'
    and 'invalid package.json for rollout validation' in entry.get('error', '')
    for entry in failed
), failed
assert any(
    entry.get('repo') == 'frontend'
    and entry.get('workspace') == 'locked-oryx'
    and 'File exists' in entry.get('error', '')
    for entry in failed
), failed
PY

python3 - <<'PY' "$fake_pg_state"
import json
import sys

state = json.loads(open(sys.argv[1]).read())
assert 'secpal__preview__broken_mole' in state['databases'], state['databases']
assert 'secpal__preview__broken_mole' in state.get('schemas', []), state.get('schemas', [])
PY

grep -qF "php:$failing_api_clone:artisan config:clear" "$provision_log"
grep -qF "composer:$guardguide_clone:install" "$provision_log"
grep -qF "npm:$guardguide_clone:ci" "$provision_log"
grep -q "php:$guardguide_clone:artisan db:seed --class=Database.*GuardGuideAccessSeeder --force" "$provision_log"
grep -qF "php:$guardguide_clone:artisan tinker --execute=" "$provision_log"
test -f "$guardguide_clone/.polyscope-secpal-provisioned.json"
test ! -f "$failing_api_clone/.polyscope-secpal-provisioned.json"
test ! -f "$failing_api_cleanup_clone/.polyscope-secpal-provisioned.json"
test ! -f "$failing_api_alias_clone/.polyscope-secpal-provisioned.json"
test ! -f "$failing_frontend_manifest_clone/.polyscope-secpal-provisioned.json"
test ! -f "$failing_frontend_io_clone/.polyscope-secpal-provisioned.json"

python3 - <<'PY' "$guardguide_clone/composer.lock"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text())
payload["packages"].append({"name": "guardguide/app", "version": "1.0.1"})
path.write_text(json.dumps(payload, indent=2) + "\n")
PY

guardguide_lockfile_summary_json="$workspace/guardguide-lockfile-summary.json"
guardguide_composer_install_count_before="$(grep -cF "composer:$guardguide_clone:install" "$provision_log" || true)"
env HOME="$home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$fake_pg_state" \
    FAIL_ON_WORKTREE="$failing_api_clone" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$guardguide_lockfile_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null || guardguide_lockfile_exit=$?

test "${guardguide_lockfile_exit:-0}" -eq 1

python3 - "$guardguide_lockfile_summary_json" <<'PY'
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
assert 'GuardGuide:steady-otter' in provisioned, provisioned
PY

test "$guardguide_composer_install_count_before" -lt "$(grep -cF "composer:$guardguide_clone:install" "$provision_log")"

schema_home_dir="$workspace/schema-home"
schema_api_clone="$schema_home_dir/.polyscope/clones/api12345/schema-badger"
schema_frontend_clone="$schema_home_dir/.polyscope/clones/fe123456/schema-badger"
schema_pg_state="$workspace/postgres-schema-state.json"
schema_summary_json="$workspace/schema-summary.json"
schema_cleanup_summary_json="$workspace/schema-cleanup-summary.json"

mkdir -p "$schema_home_dir/.local/bin" "$schema_api_clone/.git/info" "$schema_api_clone/.git/hooks" "$schema_api_clone/scripts" "$schema_frontend_clone/.git/info" "$schema_frontend_clone/.git/hooks" "$schema_frontend_clone/scripts"
cp "$home_dir/.local/bin/pre-commit" "$schema_home_dir/.local/bin/pre-commit"
seed_api_worktree_files "$schema_api_clone"
seed_node_worktree_files "$schema_frontend_clone" "frontend-schema-badger"

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

replace_registered_worktrees \
    "api12345" "$schema_api_clone" \
    "fe123456" "$schema_frontend_clone"

env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
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

python3 - <<'PY' "$schema_api_clone/.polyscope-secpal-provisioned.json"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
marker = json.loads(path.read_text())
marker.pop('preview_storage_target', None)
path.write_text(json.dumps(marker, indent=2) + "\n")
PY

cat >"$schema_api_clone/.env" <<'EOF'
APP_URL=https://api-daring-mouse.preview.secpal.dev
FRONTEND_URL=https://frontend-daring-mouse.preview.secpal.dev
DB_CONNECTION=pgsql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_DATABASE=secpal
DB_URL=postgresql://secpal@127.0.0.1:5432/secpal?search_path=secpal__preview__daring_mouse
DB_USERNAME=secpal
DB_PASSWORD=
SESSION_DOMAIN=.secpal.dev
SANCTUM_STATEFUL_DOMAINS=frontend-daring-mouse.preview.secpal.dev,daring-mouse.preview.secpal.dev,app.secpal.dev
CORS_ALLOWED_ORIGINS=https://frontend-daring-mouse.preview.secpal.dev,https://daring-mouse.preview.secpal.dev,https://app.secpal.dev
POLYSCOPE_BASE_DB_DATABASE=secpal
POLYSCOPE_PREVIEW_STORAGE_MODE=schema
POLYSCOPE_PREVIEW_SCHEMA=secpal__preview__daring_mouse
EOF

schema_recovery_summary_json="$workspace/schema-recovery-summary.json"
schema_provision_log_lines_before_recovery="$(wc -l < "$provision_log")"
env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$schema_recovery_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - <<'PY' "$schema_recovery_summary_json"
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
assert 'api:schema-badger' in provisioned, provisioned
PY

test "$schema_provision_log_lines_before_recovery" -lt "$(wc -l < "$provision_log")"
grep -qF 'APP_URL=https://api-schema-badger.preview.secpal.dev' "$schema_api_clone/.env"
grep -qF 'FRONTEND_URL=https://frontend-schema-badger.preview.secpal.dev' "$schema_api_clone/.env"
grep -qF 'DB_URL=postgresql://secpal@127.0.0.1:5432/secpal?search_path=secpal__preview__schema_badger' "$schema_api_clone/.env"
grep -qF 'POLYSCOPE_PREVIEW_SCHEMA=secpal__preview__schema_badger' "$schema_api_clone/.env"

test "$(grep -cF "php:$schema_api_clone:artisan migrate --force" "$provision_log")" -eq 2
test "$(grep -cF 'CREATE SCHEMA IF NOT EXISTS "secpal__preview__schema_badger"' "$fake_psql_log")" -eq 2

python3 - <<'PY' "$schema_frontend_clone/package-lock.json"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text())
payload["packages"][""] = {"name": "frontend-schema-badger", "version": "0.0.2"}
path.write_text(json.dumps(payload, indent=2) + "\n")
PY

schema_lockfile_summary_json="$workspace/schema-lockfile-summary.json"
schema_frontend_npm_ci_count_before="$(grep -cF "npm:$schema_frontend_clone:ci" "$provision_log" || true)"
env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
    --repo-state-file "$repos_json" \
    --nginx-output "$nginx_output" \
    --summary-output "$schema_lockfile_summary_json" \
    --skip-local-configs \
    --skip-db-sync \
    --provision-worktrees \
    > /dev/null

python3 - <<'PY' "$schema_lockfile_summary_json"
import json
import sys

summary = json.loads(open(sys.argv[1]).read())
provisioned = summary.get('provisioned_worktrees', [])
assert 'frontend:schema-badger' in provisioned, provisioned
PY

test "$schema_frontend_npm_ci_count_before" -lt "$(grep -cF "npm:$schema_frontend_clone:ci" "$provision_log")"

rm -rf "$schema_api_clone" "$schema_frontend_clone"
replace_registered_worktrees

env HOME="$schema_home_dir" \
    PATH="$service_path" \
    PROVISION_LOG="$provision_log" \
    FAKE_PSQL_LOG="$fake_psql_log" \
    FAKE_PSQL_STATE="$schema_pg_state" \
    python3 "$PYTHON_SCRIPT" \
    --workspace-root "$workspace_root" \
    --db-path "$db_path" \
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
    '"test -d vendor || composer install",\n                    "npm ci",' \
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
fake_nginx_helper="$fake_sudo_dir/secpal-polyscope-nginx-apply"
fake_server_bin="$workspace/fake-tools/polyscope-server"
fake_expose_real_log="$workspace/expose-real.log"
fake_git_real_log="$workspace/git-real.log"
fake_polyscope_bin_dir="$home_dir/.polyscope/bin"
fake_polyscope_git_dir="$home_dir/.local/lib/polyscope/bin"
fake_codex_home="$home_dir/.codex"
real_readlink_bin="$(command -v readlink)"
export REAL_READLINK_BIN="$real_readlink_bin"
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

if [[ "${1:-}" == "show" && "${2:-}" == "-p" && "${3:-}" == "User" && "${4:-}" == "--value" && "${5:-}" == "polyscope-server.service" ]]; then
    printf '%s\n' "${FAKE_SYSTEM_POLYSCOPE_SERVER_USER:-}"
fi
exit 0
STUB
chmod +x "$fake_systemctl_dir/systemctl"

cat >"$fake_systemctl_dir/readlink" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "--" ]]; then
    echo "readlink: unsupported option: --" >&2
    exit 64
fi
exec "$REAL_READLINK_BIN" "$@"
STUB
chmod +x "$fake_systemctl_dir/readlink"

cat >"$fake_sudo_dir/sudo" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SUDO_LOG"

if [[ "${1:-}" == "-n" && "${2:-}" == "-k" && "${3:-}" == "true" ]]; then
    exit 0
fi
if [[ "${1:-}" == "-n" && "${2:-}" == "true" ]]; then
    exit 98
fi

if [[ "${1:-}" == "-k" && "${2:-}" == "-n" ]]; then
    shift 2
elif [[ "${1:-}" == "-n" ]]; then
    shift
fi

exec "$@"
STUB
chmod +x "$fake_sudo_dir/sudo"

cat >"$fake_nginx_helper" <<'STUB'
#!/usr/bin/env bash
if [[ $# -eq 0 || ( $# -eq 1 && "$1" == "--check" ) ]]; then
    exit 0
fi
exit 64
STUB
chmod +x "$fake_nginx_helper"
export POLYSCOPE_NGINX_HELPER="$fake_nginx_helper"
export POLYSCOPE_TEST_ALLOW_NGINX_HELPER_OVERRIDE=1

# Production installation must persist the one fixed root-owned helper path,
# even if an older broad sudo rule would make an arbitrary override executable.
custom_helper_home_dir="$workspace/custom-helper-home"
custom_helper_bin_dir="$workspace/custom-helper-bin"
custom_helper_unit_dir="$workspace/custom-helper-units"
custom_helper_error="$workspace/custom-helper-install.error"
custom_helper_exit=0
mkdir -p "$custom_helper_home_dir/.polyscope/bin"
env HOME="$custom_helper_home_dir" \
    POLYSCOPE_NGINX_HELPER="$fake_nginx_helper" \
    POLYSCOPE_TEST_ALLOW_NGINX_HELPER_OVERRIDE=0 \
    bash "$INSTALL_SCRIPT" \
        --bin-dir "$custom_helper_bin_dir" \
        --unit-dir "$custom_helper_unit_dir" \
        --polyscope-server-bin "$fake_server_bin" \
        2>"$custom_helper_error" \
    || custom_helper_exit=$?
if [[ "$custom_helper_exit" -eq 0 ]]; then
    echo "installer must reject a non-fixed nginx helper path" >&2
    exit 1
fi
grep -qF 'nginx helper path is fixed' "$custom_helper_error"
test ! -e "$custom_helper_unit_dir/polyscope-rollout-sync.service"

# A custom rollout source is only executable as an instruction-dependent
# command when its canonical validator is present beside it. Reject an
# incomplete source bundle before installing links or systemd units.
standalone_source_dir="$workspace/standalone-rollout-source"
standalone_source_script="$standalone_source_dir/polyscope-rollout.py"
standalone_home_dir="$workspace/standalone-rollout-home"
standalone_bin_dir="$workspace/standalone-rollout-bin"
standalone_unit_dir="$workspace/standalone-rollout-units"
standalone_codex_home="$standalone_home_dir/.codex"
standalone_error="$workspace/standalone-rollout-install.error"
mkdir -p "$standalone_source_dir" "$standalone_home_dir/.polyscope/bin"
cp "$PYTHON_SCRIPT" "$standalone_source_script"
chmod +x "$standalone_source_script"
cat >"$standalone_home_dir/.polyscope/bin/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$standalone_home_dir/.polyscope/bin/expose-linux-x64"

standalone_install_exit=0
env HOME="$standalone_home_dir" \
    CODEX_HOME="$standalone_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/standalone-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" \
    --source-script "$standalone_source_script" \
    --bin-dir "$standalone_bin_dir" \
    --unit-dir "$standalone_unit_dir" \
    --polyscope-server-bin "$fake_server_bin" \
    2>"$standalone_error" \
    || standalone_install_exit=$?
if [[ "$standalone_install_exit" -eq 0 ]]; then
    echo "installer must reject a rollout source without its canonical validator" >&2
    exit 1
fi
grep -qF 'canonical instruction validator is missing or not executable' \
    "$standalone_error"
test ! -e "$standalone_bin_dir/polyscope-secpal-rollout.py"
test ! -e "$standalone_unit_dir/polyscope-rollout-sync.path"

# The sibling validator is not a complete source bundle without its pinned
# runtime dependencies. Reject that state before reporting an installation.
missing_toolchain_source_dir="$workspace/missing-toolchain-source/scripts"
missing_toolchain_source_script="$missing_toolchain_source_dir/polyscope-rollout.py"
missing_toolchain_home_dir="$workspace/missing-toolchain-home"
missing_toolchain_bin_dir="$workspace/missing-toolchain-bin"
missing_toolchain_unit_dir="$workspace/missing-toolchain-units"
missing_toolchain_error="$workspace/missing-toolchain-install.error"
mkdir -p "$missing_toolchain_source_dir" \
    "$missing_toolchain_home_dir/.polyscope/bin"
cp "$PYTHON_SCRIPT" "$missing_toolchain_source_script"
cp "$REPO_ROOT/scripts/validate-ai-instructions.sh" \
    "$missing_toolchain_source_dir/validate-ai-instructions.sh"
cp "$REPO_ROOT/scripts/polyscope_nginx.py" \
    "$missing_toolchain_source_dir/polyscope_nginx.py"
cp "$REPO_ROOT/scripts/secpal-polyscope-nginx-apply.py" \
    "$missing_toolchain_source_dir/secpal-polyscope-nginx-apply.py"
chmod +x "$missing_toolchain_source_script" \
    "$missing_toolchain_source_dir/validate-ai-instructions.sh" \
    "$missing_toolchain_source_dir/secpal-polyscope-nginx-apply.py"
cat >"$missing_toolchain_home_dir/.polyscope/bin/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$missing_toolchain_home_dir/.polyscope/bin/expose-linux-x64"

missing_toolchain_install_exit=0
env HOME="$missing_toolchain_home_dir" \
    CODEX_HOME="$missing_toolchain_home_dir/.codex" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/missing-toolchain-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" \
    --source-script "$missing_toolchain_source_script" \
    --bin-dir "$missing_toolchain_bin_dir" \
    --unit-dir "$missing_toolchain_unit_dir" \
    --polyscope-server-bin "$fake_server_bin" \
    2>"$missing_toolchain_error" \
    || missing_toolchain_install_exit=$?
if [[ "$missing_toolchain_install_exit" -eq 0 ]]; then
    echo "installer must reject a rollout validator without its pinned toolchain" >&2
    exit 1
fi
grep -qF 'rollout validator toolchain is incomplete' \
    "$missing_toolchain_error"
test ! -e "$missing_toolchain_bin_dir/polyscope-secpal-rollout.py"
test ! -e "$missing_toolchain_unit_dir/polyscope-rollout-sync.path"

# Resolving a no-whitespace alias must not bypass the installer's source-path
# restrictions and inject an unsafe path into the generated systemd unit.
spaced_source_dir="$workspace/resolved source bundle"
spaced_source_script="$spaced_source_dir/polyscope-rollout.py"
spaced_source_alias="$workspace/resolved-source-alias.py"
spaced_home_dir="$workspace/spaced-source-home"
spaced_bin_dir="$workspace/spaced-source-bin"
spaced_unit_dir="$workspace/spaced-source-units"
spaced_error="$workspace/spaced-source-install.error"
mkdir -p "$spaced_source_dir" "$spaced_home_dir/.polyscope/bin"
cp "$PYTHON_SCRIPT" "$spaced_source_script"
cp "$REPO_ROOT/scripts/validate-ai-instructions.sh" \
    "$spaced_source_dir/validate-ai-instructions.sh"
chmod +x "$spaced_source_script" \
    "$spaced_source_dir/validate-ai-instructions.sh"
ln -s "$spaced_source_script" "$spaced_source_alias"
cat >"$spaced_home_dir/.polyscope/bin/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$spaced_home_dir/.polyscope/bin/expose-linux-x64"

spaced_install_exit=0
env HOME="$spaced_home_dir" \
    CODEX_HOME="$spaced_home_dir/.codex" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/spaced-source-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" \
    --source-script "$spaced_source_alias" \
    --bin-dir "$spaced_bin_dir" \
    --unit-dir "$spaced_unit_dir" \
    --polyscope-server-bin "$fake_server_bin" \
    2>"$spaced_error" \
    || spaced_install_exit=$?
if [[ "$spaced_install_exit" -eq 0 ]]; then
    echo "installer must revalidate a resolved rollout source path" >&2
    exit 1
fi
grep -qF 'resolved rollout source script path must not contain whitespace' \
    "$spaced_error"
test ! -e "$spaced_bin_dir/polyscope-secpal-rollout.py"
test ! -e "$spaced_unit_dir/polyscope-rollout-sync.path"

# The privileged helper accepts one fixed manifest path. Reject an override
# before installing a user unit that could never complete successfully.
custom_manifest_home_dir="$workspace/custom-manifest-home"
custom_manifest_bin_dir="$workspace/custom-manifest-bin"
custom_manifest_unit_dir="$workspace/custom-manifest-units"
custom_manifest_error="$workspace/custom-manifest-install.error"
custom_manifest_exit=0
mkdir -p "$custom_manifest_home_dir/.polyscope/bin"
cat >"$custom_manifest_home_dir/.polyscope/bin/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$custom_manifest_home_dir/.polyscope/bin/expose-linux-x64"
env HOME="$custom_manifest_home_dir" \
    CODEX_HOME="$custom_manifest_home_dir/.codex" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/custom-manifest-sudo.log" \
    POLYSCOPE_NGINX_HELPER="$fake_nginx_helper" \
    POLYSCOPE_NGINX_MANIFEST="$custom_manifest_home_dir/custom-manifest.json" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" \
        --bin-dir "$custom_manifest_bin_dir" \
        --unit-dir "$custom_manifest_unit_dir" \
        --polyscope-server-bin "$fake_server_bin" \
        2>"$custom_manifest_error" \
    || custom_manifest_exit=$?
if [[ "$custom_manifest_exit" -eq 0 ]]; then
    echo "installer must reject a non-fixed nginx manifest path" >&2
    exit 1
fi
grep -qF 'nginx manifest path is fixed' "$custom_manifest_error"
test ! -e "$custom_manifest_bin_dir/polyscope-secpal-rollout.py"
test ! -e "$custom_manifest_unit_dir/polyscope-rollout-sync.service"

env HOME="$home_dir" \
    CODEX_HOME="$fake_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"

test -L "$fake_bin_dir/polyscope-secpal-rollout.py"
test -x "$fake_bin_dir/polyscope-secpal-rollout.py"
test -L "$fake_bin_dir/reap-polyscope-clones.py"
test -x "$fake_bin_dir/reap-polyscope-clones.py"
test -L "$fake_bin_dir/polyscope-expose-wrapper.sh"
test -x "$fake_bin_dir/polyscope-expose-wrapper.sh"
test -L "$fake_bin_dir/polyscope-git-wrapper.sh"
test -x "$fake_bin_dir/polyscope-git-wrapper.sh"
test -L "$fake_codex_home/AGENTS.md"
test "$(readlink "$fake_codex_home/AGENTS.md")" = "$REPO_ROOT/templates/polyscope-codex-AGENTS.md"
# shellcheck disable=SC2016 # Backticks are literal Markdown in the expected text.
grep -qF 'Treat every entry in `workspace_roots` as a separate repository' "$fake_codex_home/AGENTS.md"
grep -qF 'select **Use plan for Autopilot**' "$fake_codex_home/AGENTS.md"
grep -qF 'must not attempt any side effect' "$fake_codex_home/AGENTS.md"
grep -qF 'Never attribute that denial to the user' "$fake_codex_home/AGENTS.md"
grep -qF 'Delegate only materially independent repository scopes' "$fake_codex_home/AGENTS.md"
grep -qF 'Preserve a branch or worktree already provisioned by Polyscope' "$fake_codex_home/AGENTS.md"
# shellcheck disable=SC2016 # Backticks are literal Markdown in the expected text.
if grep -qiE 'must rename|rename the branch before|must switch to `main`|stable/dev|runtime cop(y|ies)' \
    "$fake_codex_home/AGENTS.md"; then
    echo "global Codex instructions must not force branch changes or runtime-copy modes" >&2
    exit 1
fi
test -L "$fake_polyscope_git_dir/git"
test -x "$fake_polyscope_git_dir/git"
test "$(readlink "$fake_polyscope_git_dir/git")" = "$fake_bin_dir/polyscope-git-wrapper.sh"
test -L "$fake_polyscope_bin_dir/expose-linux-x64"
test -x "$fake_polyscope_bin_dir/expose-linux-x64"
test -x "$fake_polyscope_bin_dir/expose-linux-x64.real"
test "$(readlink "$fake_polyscope_bin_dir/expose-linux-x64")" = "$fake_bin_dir/polyscope-expose-wrapper.sh"

# Existing user-managed global guidance must not be replaced by rollout.
custom_codex_home="$workspace/custom-codex-home"
mkdir -p "$custom_codex_home"
printf '# User-managed Codex guidance\n' >"$custom_codex_home/AGENTS.md"
custom_codex_install_exit=0
env HOME="$home_dir" \
    CODEX_HOME="$custom_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin" 2>/dev/null \
    || custom_codex_install_exit=$?
if [[ "$custom_codex_install_exit" -eq 0 ]]; then
    echo "installer must refuse to overwrite user-managed Codex instructions" >&2
    exit 1
fi
grep -qxF '# User-managed Codex guidance' "$custom_codex_home/AGENTS.md"

# A dangling link created by an older checkout must be refreshed, while an
# unrelated symlink remains protected as user-managed guidance.
stale_codex_home="$workspace/stale-codex-home"
stale_codex_target="$workspace/old-checkout/templates/polyscope-codex-AGENTS.md"
mkdir -p "$stale_codex_home"
touch "$stale_codex_home/AGENTS.override.md"
ln -s "$stale_codex_target" "$stale_codex_home/AGENTS.md"
env HOME="$home_dir" \
    CODEX_HOME="$stale_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"
test "$(readlink "$stale_codex_home/AGENTS.md")" = "$REPO_ROOT/templates/polyscope-codex-AGENTS.md"

unrelated_codex_home="$workspace/unrelated-codex-home"
unrelated_codex_source="$workspace/unrelated-guidance.md"
mkdir -p "$unrelated_codex_home"
printf '# Unrelated linked guidance\n' >"$unrelated_codex_source"
ln -s "$unrelated_codex_source" "$unrelated_codex_home/AGENTS.md"
unrelated_codex_install_exit=0
env HOME="$home_dir" \
    CODEX_HOME="$unrelated_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin" 2>/dev/null \
    || unrelated_codex_install_exit=$?
if [[ "$unrelated_codex_install_exit" -eq 0 ]]; then
    echo "installer must refuse to overwrite unrelated linked Codex instructions" >&2
    exit 1
fi
test "$(readlink "$unrelated_codex_home/AGENTS.md")" = "$unrelated_codex_source"

# Non-empty global overrides take precedence over AGENTS.md and must not let
# the installer report that inactive Polyscope guidance was installed.
override_codex_home="$workspace/override-codex-home"
override_codex_error="$workspace/override-codex-error.log"
mkdir -p "$override_codex_home"
printf '# User override\n' >"$override_codex_home/AGENTS.override.md"
override_codex_install_exit=0
env HOME="$home_dir" \
    CODEX_HOME="$override_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin" 2>"$override_codex_error" \
    || override_codex_install_exit=$?
if [[ "$override_codex_install_exit" -eq 0 ]]; then
    echo "installer must reject a non-empty global Codex override" >&2
    exit 1
fi
grep -qF 'AGENTS.override.md takes precedence' "$override_codex_error"
grep -qxF '# User override' "$override_codex_home/AGENTS.override.md"
test ! -e "$override_codex_home/AGENTS.md"

# Re-running the installer after the expose binary has been wrapped must stay idempotent.
env HOME="$home_dir" \
    CODEX_HOME="$fake_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$fake_bin_dir" --unit-dir "$fake_unit_dir" --polyscope-server-bin "$fake_server_bin"

# If the wrapped Expose path is replaced with the original real binary while .real already exists,
# the installer must still repair it idempotently instead of failing.
rm -f "$fake_polyscope_bin_dir/expose-linux-x64"
cp "$fake_polyscope_bin_dir/expose-linux-x64.real" "$fake_polyscope_bin_dir/expose-linux-x64"

env HOME="$home_dir" \
    CODEX_HOME="$fake_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
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
    CODEX_HOME="$fake_codex_home" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$fake_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$workspace/user-sudo.log" \
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
system_server_user="$(id -un)"
mkdir -p "$system_bin_dir" "$system_user_unit_dir" "$system_polyscope_bin_dir" "$system_polyscope_git_dir" "$system_fragment_dir"
printf '[Unit]\nDescription=Polyscope Server\n' > "$system_fragment_path"
system_component_stage="$workspace/system-component-stage"
DESTDIR="$system_component_stage" \
    "$REPO_ROOT/scripts/install-polyscope-system-components.sh" --stage-only >/dev/null
mkdir -p "$system_dropin_dir"
cp "$system_component_stage/etc/systemd/system/polyscope-server.service.d/zz-secpal-runtime.conf" \
    "$system_dropin_dir/zz-secpal-runtime.conf"
system_dropin_hash_before="$(file_sha256 "$system_dropin_dir/zz-secpal-runtime.conf")"

# A stale privileged drop-in must fail the unprivileged installer before it
# creates any links or user units. The system-component installer is the only
# writer for this root-owned contract.
stale_system_dropin_dir="$workspace/stale-system-service-units/polyscope-server.service.d"
stale_system_bin_dir="$workspace/stale-system-bin"
stale_system_unit_dir="$workspace/stale-system-user-units"
stale_system_error="$workspace/stale-system-install.error"
mkdir -p "$stale_system_dropin_dir"
printf '[Service]\nUser=secpal\n' >"$stale_system_dropin_dir/zz-secpal-runtime.conf"
stale_system_exit=0
env HOME="$system_home_dir" \
    CODEX_HOME="$system_home_dir/.codex-stale" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$system_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$system_sudo_log" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_FRAGMENT="$system_fragment_path" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_USER="$system_server_user" \
    POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR="$stale_system_dropin_dir" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$stale_system_bin_dir" --unit-dir "$stale_system_unit_dir" --polyscope-server-bin "$fake_server_bin" \
    2>"$stale_system_error" \
    || stale_system_exit=$?
if [[ "$stale_system_exit" -eq 0 ]]; then
    echo "unprivileged installer must reject stale system components" >&2
    exit 1
fi
grep -qF 'reviewed system server drop-in is incomplete' "$stale_system_error"
test ! -e "$stale_system_bin_dir/polyscope-secpal-rollout.py"
test ! -e "$stale_system_unit_dir/polyscope-rollout-sync.service"

cat >"$system_polyscope_bin_dir/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_EXPOSE_REAL_LOG"
exit 0
STUB
chmod +x "$system_polyscope_bin_dir/expose-linux-x64"

env HOME="$system_home_dir" \
    CODEX_HOME="$system_home_dir/.codex" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$system_systemctl_log" \
    SUDO_BIN="$fake_sudo_dir/sudo" \
    SUDO_LOG="$system_sudo_log" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_FRAGMENT="$system_fragment_path" \
    FAKE_SYSTEM_POLYSCOPE_SERVER_USER="$system_server_user" \
    POLYSCOPE_SYSTEM_SERVER_DROPIN_DIR="$system_dropin_dir" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" --bin-dir "$system_bin_dir" --unit-dir "$system_user_unit_dir" --polyscope-server-bin "$fake_server_bin"

test ! -e "$system_user_unit_dir/polyscope-server.service"
test -f "$system_dropin_dir/zz-secpal-runtime.conf"
test "$(file_sha256 "$system_dropin_dir/zz-secpal-runtime.conf")" = "$system_dropin_hash_before"
grep -q 'ExecStart=/home/secpal/.local/bin/polyscope-server serve --host 127.0.0.1 --port 4321' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'ExecStartPost=/usr/bin/env bash -lc ' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'Environment=PATH=/home/secpal/.local/lib/polyscope/bin:/home/secpal/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'Environment=SSH_AUTH_SOCK=/run/user/1000/openssh_agent' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$system_dropin_dir/zz-secpal-runtime.conf"
grep -q 'After=network-online.target' "$system_user_unit_dir/polyscope-rollout-sync.service"
grep -q 'After=polyscope-rollout-sync.service' "$system_user_unit_dir/polyscope-worktree-provision.service"
if grep -Eq '^(daemon-reload|enable --now polyscope-server\.service|restart polyscope-server\.service)$' "$system_systemctl_log"; then
  echo "unprivileged installer must not mutate the system service" >&2
  exit 1
fi
grep -q '^--user disable --now polyscope-server.service$' "$system_systemctl_log"
grep -q '^--user daemon-reload$' "$system_systemctl_log"
grep -q '^--user enable --now polyscope-rollout-sync.path$' "$system_systemctl_log"
grep -q '^--user start polyscope-rollout-sync.service$' "$system_systemctl_log"
grep -q '^--user enable --now polyscope-worktree-provision.path$' "$system_systemctl_log"
grep -q '^--user enable --now polyscope-worktree-provision.timer$' "$system_systemctl_log"
if [[ "$(grep -n '^--user start polyscope-rollout-sync.service$' "$system_systemctl_log" | tail -n1 | cut -d: -f1)" -ge "$(grep -n '^--user enable --now polyscope-worktree-provision.timer$' "$system_systemctl_log" | tail -n1 | cut -d: -f1)" ]]; then
  echo "system-scope install must finish the initial sync before enabling the provision timer" >&2
  exit 1
fi
if grep -q '^--user start polyscope-worktree-provision.service$' "$system_systemctl_log"; then
  echo "system-scope install must not start polyscope-worktree-provision.service directly once the timer is enabled" >&2
  exit 1
fi

grep -q 'ExecStart=.*/polyscope-server serve --host 127.0.0.1 --port 4321' "$fake_unit_dir/polyscope-server.service"
grep -q 'ExecStartPost=/usr/bin/env bash -lc ' "$fake_unit_dir/polyscope-server.service"
grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-server.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-server.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-server.service"
grep -q 'polyscope-secpal-rollout.py --workspace-root ' "$fake_unit_dir/polyscope-server.service"
grep -q 'Restart=on-failure' "$fake_unit_dir/polyscope-server.service"
grep -q 'After=polyscope-server.service' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root .* --polyscope-api-base http://127.0.0.1:4321/api' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'ExecStart=.* --install-nginx$' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root ' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q "Environment=POLYSCOPE_SUDO_BIN=$fake_sudo_dir/sudo" "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q 'Environment=POLYSCOPE_NGINX_HELPER=/usr/local/libexec/secpal-polyscope-nginx-apply' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q -- '--nginx-manifest-output .*nginx-manifest.json --install-nginx$' "$fake_unit_dir/polyscope-rollout-sync.service"
grep -q '/api/AGENTS.md' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -q '/GuardGuide/AGENTS.md' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -q '/templates/polyscope-codex-AGENTS.md' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/polyscope-rollout\.py$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/validate-ai-instructions\.sh$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/package-lock\.json$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/node_modules/\.package-lock\.json$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/polyscope_nginx\.py$' "$fake_unit_dir/polyscope-rollout-sync.path"
grep -qE '^PathChanged=.*/scripts/secpal-polyscope-nginx-apply\.py$' "$fake_unit_dir/polyscope-rollout-sync.path"
if grep -qF '/../' "$fake_unit_dir/polyscope-rollout-sync.path"; then
    echo "rollout sync watcher paths must be normalized" >&2
    exit 1
fi
grep -q 'After=polyscope-rollout-sync.service' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'StartLimitIntervalSec=300' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'StartLimitBurst=5' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'ExecStart=.*/polyscope-secpal-rollout.py --workspace-root .* --polyscope-api-base http://127.0.0.1:4321/api --clone-root .* --skip-local-configs --skip-db-sync --provision-worktrees' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q '^OnStartupSec=30s$' "$fake_unit_dir/polyscope-worktree-provision.timer"
grep -q '^OnUnitActiveSec=3min$' "$fake_unit_dir/polyscope-worktree-provision.timer"
grep -q '^Persistent=true$' "$fake_unit_dir/polyscope-worktree-provision.timer"
grep -q 'ExecStart=.*/reap-polyscope-clones.py --polyscope-home .* --clone-root .* --grace-period 7d' "$fake_unit_dir/polyscope-clone-reaper.service"
grep -q '^OnStartupSec=10min$' "$fake_unit_dir/polyscope-clone-reaper.timer"
grep -q '^OnUnitActiveSec=1d$' "$fake_unit_dir/polyscope-clone-reaper.timer"
grep -q '^Persistent=true$' "$fake_unit_dir/polyscope-clone-reaper.timer"

default_readiness_retry_seconds="$(sed -nE 's/.*POLYSCOPE_EXPOSE_WRAPPER_RETRY_SECONDS:-([0-9]+).*/\1/p' "$REPO_ROOT/scripts/polyscope-expose-wrapper.sh")"
default_readiness_max_attempts="$(sed -nE 's/.*POLYSCOPE_EXPOSE_WRAPPER_MAX_ATTEMPTS:-([0-9]+).*/\1/p' "$REPO_ROOT/scripts/polyscope-expose-wrapper.sh")"
if (( (default_readiness_max_attempts - 1) * default_readiness_retry_seconds < 600 )); then
    echo "API preview readiness wait must cover fallback provisioning after the three-minute timer" >&2
    exit 1
fi

grep -q "Environment=PATH=$fake_polyscope_git_dir:$fake_bin_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin" "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'Environment=SSH_AUTH_SOCK=%t/openssh_agent' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -q 'Environment=POLYSCOPE_REAL_GIT_BIN=' "$fake_unit_dir/polyscope-worktree-provision.service"
grep -qE '^PathChanged=.*/\.polyscope/polyscope\.db$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -qE '^PathModified=.*/\.polyscope/polyscope\.db-wal$' "$fake_unit_dir/polyscope-worktree-provision.path"
if grep -qE '^PathModified=.*/\.polyscope/clones$' "$fake_unit_dir/polyscope-worktree-provision.path"; then
  echo "worktree provision path must not watch clone contents it modifies" >&2
  exit 1
fi
grep -qE '^PathChanged=.*/api/polyscope\.local\.json$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -qE '^PathChanged=.*/frontend/polyscope\.local\.json$' "$fake_unit_dir/polyscope-worktree-provision.path"
grep -qF 'fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)' "$workspace_root/frontend/polyscope.local.json"
grep -qF '.polyscope-preview-stage' "$workspace_root/frontend/polyscope.local.json"
grep -qF 'build.lock' "$workspace_root/frontend/polyscope.local.json"
grep -q 'daemon-reload' "$fake_systemctl_log"
grep -q 'enable --now polyscope-server.service' "$fake_systemctl_log"
grep -q 'restart polyscope-server.service' "$fake_systemctl_log"
grep -q 'enable --now polyscope-rollout-sync.path' "$fake_systemctl_log"
grep -q 'start polyscope-rollout-sync.service' "$fake_systemctl_log"
grep -q 'enable --now polyscope-worktree-provision.path' "$fake_systemctl_log"
grep -q 'enable --now polyscope-worktree-provision.timer' "$fake_systemctl_log"
grep -q 'enable --now polyscope-clone-reaper.timer' "$fake_systemctl_log"
if [[ "$(grep -n 'start polyscope-rollout-sync.service' "$fake_systemctl_log" | tail -n1 | cut -d: -f1)" -ge "$(grep -n 'enable --now polyscope-worktree-provision.timer' "$fake_systemctl_log" | tail -n1 | cut -d: -f1)" ]]; then
  echo "installer must finish the initial sync before enabling the provision timer" >&2
  exit 1
fi
if grep -q 'start polyscope-worktree-provision.service' "$fake_systemctl_log"; then
  echo "installer must not start polyscope-worktree-provision.service directly once the timer is enabled" >&2
  exit 1
fi
if grep -qF -- '-n -k true' "$workspace/user-sudo.log"; then
  echo "installer must not test generic passwordless sudo" >&2
  exit 1
fi
grep -qF -- "-k -n $fake_nginx_helper --check" "$workspace/user-sudo.log"

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
    CODEX_HOME="$no_sudo_home_dir/.codex" \
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

# The user-scoped rollout sync also installs nginx and must therefore reject
# configurations that cannot obtain unattended privileges before writing units.
no_sudo_user_home_dir="$workspace/no-sudo-user-home"
no_sudo_user_bin_dir="$workspace/no-sudo-user-bin"
no_sudo_user_unit_dir="$workspace/no-sudo-user-units"
no_sudo_user_exit=0
mkdir -p "$no_sudo_user_home_dir/.polyscope/bin"
cat >"$no_sudo_user_home_dir/.polyscope/bin/expose-linux-x64" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$no_sudo_user_home_dir/.polyscope/bin/expose-linux-x64"
env HOME="$no_sudo_user_home_dir" \
    CODEX_HOME="$no_sudo_user_home_dir/.codex" \
    WORKSPACE_ROOT="$workspace_root" \
    SYSTEMCTL_BIN="$fake_systemctl_dir/systemctl" \
    SYSTEMCTL_LOG="$no_sudo_systemctl_log" \
    SUDO_BIN="$no_sudo_sudo_dir/sudo" \
    PATH="$fake_systemctl_dir:$PATH" \
    bash "$INSTALL_SCRIPT" \
        --bin-dir "$no_sudo_user_bin_dir" \
        --unit-dir "$no_sudo_user_unit_dir" \
        --polyscope-server-bin "$fake_server_bin" \
        --polyscope-server-scope user \
        2>/dev/null || no_sudo_user_exit=$?
if [[ "$no_sudo_user_exit" -eq 0 ]]; then
    echo "installer must refuse user scope when unattended nginx privileges are unavailable" >&2
    exit 1
fi
test ! -e "$no_sudo_user_unit_dir/polyscope-rollout-sync.service"

# installer must also refuse when --polyscope-server-scope system is forced but no unit exists
no_unit_exit=0
env HOME="$no_sudo_home_dir" \
    CODEX_HOME="$no_sudo_home_dir/.codex" \
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
fake_curl_bin="$workspace/fake-tools/curl"
fake_curl_log="$workspace/fake-curl.log"
fake_curl_attempt_file="$workspace/fake-curl-attempt"
cat >"$fake_curl_bin" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >> "$FAKE_CURL_LOG"
attempt=0
if [[ -f "$FAKE_CURL_ATTEMPT_FILE" ]]; then
    attempt="$(cat "$FAKE_CURL_ATTEMPT_FILE")"
fi
attempt=$((attempt + 1))
printf '%s\n' "$attempt" > "$FAKE_CURL_ATTEMPT_FILE"

if [[ "${FAKE_CURL_ALWAYS_FAIL:-0}" == "1" || "$attempt" -lt 2 ]]; then
    exit 1
fi

printf '%s' "${FAKE_CURL_HTTP_STATUS:-200}"
STUB
chmod +x "$fake_curl_bin"

env HOME="$home_dir" \
    PATH="$workspace/fake-tools:$PATH" \
    FAKE_CURL_LOG="$fake_curl_log" \
    FAKE_CURL_ATTEMPT_FILE="$fake_curl_attempt_file" \
    POLYSCOPE_EXPOSE_WRAPPER_RETRY_SECONDS=0 \
    POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://api-auto-hawk.preview.secpal.dev:443 >"$preview_wrapper_out"

grep -q 'Shared site              https://api-auto-hawk.preview.secpal.dev' "$preview_wrapper_out"
grep -q 'Public URL               https://api-auto-hawk.preview.secpal.dev' "$preview_wrapper_out"
test "$(cat "$fake_curl_attempt_file")" = "2"
grep -qx -- '-fsS --max-time 3 -o /dev/null -w %{http_code} https://api-auto-hawk.preview.secpal.dev/health/ready' "$fake_curl_log"

path_preview_wrapper_out="$workspace/expose-wrapper-path-preview.out"
env HOME="$home_dir" \
    PATH="$workspace/fake-tools:$PATH" \
    FAKE_CURL_LOG="$fake_curl_log" \
    FAKE_CURL_ATTEMPT_FILE="$fake_curl_attempt_file" \
    POLYSCOPE_EXPOSE_WRAPPER_RETRY_SECONDS=0 \
    POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://api-path-hawk.preview.secpal.dev/some/path >"$path_preview_wrapper_out"

grep -q 'Public URL               https://api-path-hawk.preview.secpal.dev/some/path' "$path_preview_wrapper_out"
test "$(cat "$fake_curl_attempt_file")" = "3"
grep -qx -- '-fsS --max-time 3 -o /dev/null -w %{http_code} https://api-path-hawk.preview.secpal.dev/health/ready' "$fake_curl_log"

env HOME="$home_dir" \
    PATH="$workspace/fake-tools:$PATH" \
    FAKE_CURL_LOG="$fake_curl_log" \
    FAKE_CURL_ATTEMPT_FILE="$fake_curl_attempt_file" \
    POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://frontend-auto-hawk.preview.secpal.dev:443 >/dev/null

test "$(cat "$fake_curl_attempt_file")" = "3"

physical_preview_clone_root="$workspace/physical-preview-clones"
physical_preview_worktree="$physical_preview_clone_root/fe123456/misty-vulture-26c1f2f1"
physical_preview_wrapper_out="$workspace/expose-wrapper-physical-preview.out"
mkdir -p "$physical_preview_worktree"
cat >"$physical_preview_worktree/.polyscope-secpal-provisioned.json" <<'JSON'
{
  "repo": "frontend",
  "workspace": "misty-vulture",
  "physical_workspace": "misty-vulture-26c1f2f1"
}
JSON

(
    cd "$workspace"
    env HOME="$home_dir" \
        PATH="$workspace/fake-tools:$PATH" \
        POLYSCOPE_CLONE_ROOT="$physical_preview_clone_root" \
        POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
        "$fake_polyscope_bin_dir/expose-linux-x64" \
        share https://frontend-misty-vulture-26c1f2f1.preview.secpal.dev:443
) >"$physical_preview_wrapper_out"

grep -q 'Shared site              https://frontend-misty-vulture.preview.secpal.dev' "$physical_preview_wrapper_out"
grep -q 'Public URL               https://frontend-misty-vulture.preview.secpal.dev' "$physical_preview_wrapper_out"
if grep -q 'misty-vulture-26c1f2f1' "$physical_preview_wrapper_out"; then
    echo "successful preview announcement must not expose the physical hash-suffixed host" >&2
    exit 1
fi

canonical_hash_workspace="$physical_preview_clone_root/fe123456/release-deadbeef"
canonical_hash_wrapper_out="$workspace/expose-wrapper-canonical-hash-preview.out"
mkdir -p "$canonical_hash_workspace"
cat >"$canonical_hash_workspace/.polyscope-secpal-provisioned.json" <<'JSON'
{
  "repo": "frontend",
  "workspace": "release-deadbeef",
  "physical_workspace": "release-deadbeef"
}
JSON

(
    cd "$workspace"
    env HOME="$home_dir" \
        POLYSCOPE_CLONE_ROOT="$physical_preview_clone_root" \
        POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
        "$fake_polyscope_bin_dir/expose-linux-x64" \
        share https://frontend-release-deadbeef.preview.secpal.dev:443
) >"$canonical_hash_wrapper_out"

grep -q 'Public URL               https://frontend-release-deadbeef.preview.secpal.dev' "$canonical_hash_wrapper_out"

generic_hash_wrapper_out="$workspace/expose-wrapper-generic-hash-preview.out"
env HOME="$home_dir" \
    POLYSCOPE_CLONE_ROOT="$physical_preview_clone_root" \
    POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" \
    share https://release-deadbeef.preview.secpal.dev:443 >"$generic_hash_wrapper_out"
grep -q 'Public URL               https://release-deadbeef.preview.secpal.dev' "$generic_hash_wrapper_out"

unprovisioned_physical_worktree="$workspace/unprovisioned-physical-preview/misty-vulture-26c1f2f1"
unprovisioned_clone_root="$workspace/unprovisioned-physical-clones"
unprovisioned_physical_wrapper_out="$workspace/expose-wrapper-unprovisioned-physical-preview.out"
mkdir -p "$unprovisioned_physical_worktree" "$unprovisioned_clone_root"
if (
    cd "$unprovisioned_physical_worktree"
    env HOME="$home_dir" \
        POLYSCOPE_CLONE_ROOT="$unprovisioned_clone_root" \
        POLYSCOPE_EXPOSE_WRAPPER_EXIT_AFTER_ANNOUNCE=1 \
        "$fake_polyscope_bin_dir/expose-linux-x64" \
        share https://frontend-misty-vulture-26c1f2f1.preview.secpal.dev:443
) >"$unprovisioned_physical_wrapper_out" 2>&1; then
    echo "physical hash-suffixed preview must not be announced without canonical provisioning metadata" >&2
    exit 1
fi
grep -q 'refusing to announce physical hash-suffixed preview URL' "$unprovisioned_physical_wrapper_out"
if grep -q 'Public URL' "$unprovisioned_physical_wrapper_out"; then
    echo "physical hash-suffixed preview must never be exposed as the public URL" >&2
    exit 1
fi

failed_preview_wrapper_out="$workspace/expose-wrapper-preview-failed.out"
if env HOME="$home_dir" \
    PATH="$workspace/fake-tools:$PATH" \
    FAKE_CURL_LOG="$fake_curl_log" \
    FAKE_CURL_ATTEMPT_FILE="$fake_curl_attempt_file" \
    FAKE_CURL_ALWAYS_FAIL=1 \
    POLYSCOPE_EXPOSE_WRAPPER_MAX_ATTEMPTS=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://api-failing-hawk.preview.secpal.dev:443 >"$failed_preview_wrapper_out" 2>&1; then
    echo "unready API preview must fail instead of announcing readiness" >&2
    exit 1
fi

grep -q 'API preview did not become ready after 1 attempts' "$failed_preview_wrapper_out"
if grep -q 'Public URL' "$failed_preview_wrapper_out"; then
    echo "unready API preview must not announce a public URL" >&2
    exit 1
fi

redirect_preview_wrapper_out="$workspace/expose-wrapper-preview-redirect.out"
if env HOME="$home_dir" \
    PATH="$workspace/fake-tools:$PATH" \
    FAKE_CURL_LOG="$fake_curl_log" \
    FAKE_CURL_ATTEMPT_FILE="$fake_curl_attempt_file" \
    FAKE_CURL_HTTP_STATUS=302 \
    POLYSCOPE_EXPOSE_WRAPPER_MAX_ATTEMPTS=1 \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://api-redirect-hawk.preview.secpal.dev:443 >"$redirect_preview_wrapper_out" 2>&1; then
    echo "redirecting API preview must not announce readiness" >&2
    exit 1
fi

grep -q 'API preview did not become ready after 1 attempts' "$redirect_preview_wrapper_out"
if grep -q 'Public URL' "$redirect_preview_wrapper_out"; then
    echo "redirecting API preview must not announce a public URL" >&2
    exit 1
fi

if [[ -s "$fake_expose_real_log" ]]; then
    echo "preview-domain Expose wrapper must not invoke the real Expose binary" >&2
    exit 1
fi

env HOME="$home_dir" \
    FAKE_EXPOSE_REAL_LOG="$fake_expose_real_log" \
    "$fake_polyscope_bin_dir/expose-linux-x64" share https://example.com:443 >/dev/null

grep -q 'share https://example.com:443' "$fake_expose_real_log"

# Keep the package-1 security boundaries attached to the established rollout
# regression entry point used by repository validation.
bash "$SCRIPT_DIR/polyscope-package-1-closure.sh"
bash "$SCRIPT_DIR/polyscope-nginx-helper.sh"
bash "$SCRIPT_DIR/polyscope-system-installer.sh"
