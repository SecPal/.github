<!--
SPDX-FileCopyrightText: 2025-2026 SecPal Contributors
SPDX-License-Identifier: CC0-1.0
-->

# Git Hook Setup and Troubleshooting

SecPal keeps automatic Git hooks fast. Commits run focused formatting and
policy checks through pre-commit, and commit messages pass through the shared
attribution-cleanup hook. The complete repository validation suite is not a
pre-push hook.

## Install Managed Hooks

For one repository:

```bash
./scripts/setup-pre-commit.sh
```

For every repository in a SecPal workspace:

```bash
cd .github
./setup-hooks.sh
```

The workspace setup installs pre-commit and commit-msg hooks. It also removes a
legacy `pre-push` symlink only when that symlink resolves to the same
repository's `scripts/preflight.sh`. Regular hook files and symlinks to custom
targets are preserved.

## Validation Workflow

Run the smallest relevant validation while iterating. Before handoff, use the
single Polyscope `All Checks` action when the change warrants a complete local
pass. The repository preflight remains available as an explicit command:

```bash
./scripts/preflight.sh
```

Pushes do not repeat this complete suite. Do not bypass failing commit-time
hooks; fix the reported issue.

## Verify the Installed Hooks

```bash
pre-commit run --all-files
git rev-parse --git-path hooks
ls -la "$(git rev-parse --git-path hooks)"
```

Expected managed hooks are:

- an executable `pre-commit` hook installed by the pre-commit framework;
- a `commit-msg` symlink to the shared `strip-ai-trailers.sh` script;
- no SecPal-managed `pre-push` symlink to `scripts/preflight.sh`.

A repository may still have its own custom `pre-push` hook.

## Common Problems

### `pre-commit` Is Missing

Install pre-commit with `pipx`, your operating-system package manager, or a
project virtual environment, then rerun `./scripts/setup-pre-commit.sh`.

### A Push Still Starts the Full Preflight

Inspect the hook without executing it:

```bash
hook_path="$(git rev-parse --git-path hooks)/pre-push"
ls -l "$hook_path"
readlink "$hook_path"
```

Run `.github/setup-hooks.sh` from the workspace. The script removes the old
managed symlink conservatively. If the hook is a regular file or points
somewhere else, it is custom and must be reviewed by that repository's owner.

### A Focused Check Passes but All Checks Fails

Treat the complete run as the handoff gate: reproduce the specific failure,
fix it, rerun the smallest affected check, and then rerun `All Checks` once.
Do not add another automatic full-suite invocation to compensate.

## Optional Workflow Lint

Workflow linting is enforced through pre-commit and CI. For a deliberate local
run, prefer:

```bash
pre-commit run actionlint --all-files
```

If invoking `actionlint` directly, use a short timeout to guard against
environment-specific hangs.
