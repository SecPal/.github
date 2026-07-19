#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/polyscope-package-1-closure.XXXXXX")"
trap 'rm -rf "$WORKSPACE"' EXIT

python3 -B - "$REPO_ROOT" "$WORKSPACE" <<'PY'
import importlib.util
import json
import os
import pathlib
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time

repo_root = pathlib.Path(sys.argv[1])
workspace = pathlib.Path(sys.argv[2])
script_path = repo_root / "scripts" / "polyscope-rollout.py"

spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def write_valid_instructions(root: pathlib.Path) -> None:
    root.joinpath(".github").mkdir(parents=True, exist_ok=True)
    root.joinpath(".markdownlint.json").write_text(repo_root.joinpath(".markdownlint.json").read_text())
    root.joinpath("AGENTS.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License-" "Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Runtime Instructions\n\n"
        "## Scope and Safety\n\n"
        "- Preserve existing work.\n"
    )
    root.joinpath(".github", "copilot-instructions.md").write_text(
        "<!--\n"
        "SPDX-FileCopyrightText: 2026 SecPal\n"
        "SPDX-License-" "Identifier: CC0-1.0\n"
        "-->\n\n"
        "# Test Review Profile\n\n"
        "- Review the complete diff.\n"
    )


def run_polyscope_setup(
    root: pathlib.Path,
    commands: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Execute setup exactly as Polyscope joins the generated entries."""
    return subprocess.run(
        ["bash", "-c", " && ".join(commands)],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


# Every generated native setup must enter the real canonical validator before
# any repository-specific mutation. Execute that boundary rather than merely
# inspecting source ordering.
native_source_workspace = workspace / "native source roots"
for repo_name in module.REPO_SETTINGS:
    source_root = native_source_workspace / repo_name
    write_valid_instructions(source_root)
    source_root.joinpath("package.json").write_text(
        json.dumps({"name": f"source-{repo_name}", "private": True}) + "\n"
    )
    source_root.joinpath("package-lock.json").write_text(
        json.dumps(
            {
                "name": f"source-{repo_name}",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {},
            }
        )
        + "\n"
    )
    source_root.joinpath(".env.example").write_text(
        "APP_KEY=base64:test-key\nDB_CONNECTION=sqlite\nDB_DATABASE=database/database.sqlite\n"
    )
generated_specs = module.build_repo_specs(native_source_workspace)
native_fake_bin = workspace / "native fake bin"
native_fake_bin.mkdir()
native_setup_log = workspace / "native-setup.log"
for executable in ("composer", "npm", "php"):
    fake_executable = native_fake_bin / executable
    fake_executable.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"printf '{executable}:%s\\n' \"$*\" >>\"$NATIVE_SETUP_LOG\"\n"
        f"touch .native-{executable}-invoked\n"
        + (
            "mkdir -p node_modules\n"
            "printf '{}\\n' >node_modules/.package-lock.json\n"
            "if [[ \"${1:-}\" == run && \"${2:-}\" == build && -n \"${VITE_POLYSCOPE_OUTPUT_DIR:-}\" ]]; then\n"
            "    mkdir -p \"$VITE_POLYSCOPE_OUTPUT_DIR\"\n"
            "    printf '<html></html>\\n' >\"$VITE_POLYSCOPE_OUTPUT_DIR/index.html\"\n"
            "fi\n"
            "previous=''\n"
            "for argument in \"$@\"; do\n"
            "    if [[ \"$previous\" == --outDir ]]; then\n"
            "        mkdir -p \"$argument\"\n"
            "        printf '<html></html>\\n' >\"$argument/index.html\"\n"
            "    fi\n"
            "    previous=\"$argument\"\n"
            "done\n"
            if executable == "npm"
            else "mkdir -p vendor; touch vendor/autoload.php\n"
            if executable == "composer"
            else ""
        )
        + "exit 0\n"
    )
    fake_executable.chmod(0o755)

native_env = os.environ.copy()
native_env["PATH"] = f"{native_fake_bin}:{native_env['PATH']}"
native_env["NATIVE_SETUP_LOG"] = str(native_setup_log)
native_env["POLYSCOPE_DB_PATH"] = str(workspace / "native-polyscope.db")

for repo_name, generated_spec in generated_specs.items():
    setup_commands = module.render_local_config(generated_spec).get("scripts", {}).get("setup", [])
    assert setup_commands, repo_name
    assert "--validate-instruction-worktree" in setup_commands[0], (repo_name, setup_commands)

    invalid_root = workspace / "native setup ; invalid roots" / repo_name
    write_valid_instructions(invalid_root)
    invalid_root.joinpath("AGENTS.md").write_text("# Missing SPDX metadata\n")
    invalid_root.joinpath("package.json").write_text(
        json.dumps({"name": f"invalid-{repo_name}", "private": True}) + "\n"
    )
    invalid_root.joinpath("package-lock.json").write_text(
        json.dumps(
            {
                "name": f"invalid-{repo_name}",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {},
            }
        )
        + "\n"
    )
    unrelated = invalid_root / "unrelated-sentinel"
    unrelated.write_bytes(b"unchanged")
    result = run_polyscope_setup(invalid_root, setup_commands, native_env)
    assert result.returncode != 0, (repo_name, result.stdout, result.stderr)
    assert "canonical AI-instruction validation failed" in result.stderr, (
        repo_name,
        result.stdout,
        result.stderr,
    )
    assert "Canonical AI-instruction validation passed" not in result.stdout, result.stdout

    for forbidden in (
        ".env",
        "node_modules",
        "vendor",
        "database.sqlite",
        ".native-composer-invoked",
        ".native-npm-invoked",
        ".native-php-invoked",
        ".polyscope-secpal-provisioned.json",
    ):
        assert not invalid_root.joinpath(forbidden).exists(), (
            repo_name,
            forbidden,
            setup_commands,
            result.stdout,
            result.stderr,
            native_setup_log.read_text() if native_setup_log.exists() else "",
        )
    assert unrelated.read_bytes() == b"unchanged"

# The generated setup contract must be a single native-runner entry. Within
# that entry, multiline commands remain ordered and any failure stops every
# later command.
for repo_name, generated_spec in generated_specs.items():
    setup_commands = module.render_local_config(generated_spec)["scripts"]["setup"]
    assert len(setup_commands) == 1, (repo_name, setup_commands)

ordered_root = workspace / "ordered setup root with spaces ; and shell chars"
ordered_root.mkdir(parents=True)
ordered_log = ordered_root / "order.log"
ordered_commands = [
    "printf 'first\\n' >>order.log",
    "for item in second; do printf '%s\\n' \"$item\" >>order.log; done",
    "printf 'third\\n' >>order.log",
]
ordered_setup = module.build_fail_closed_setup_command(ordered_commands)
ordered_result = run_polyscope_setup(ordered_root, [ordered_setup], os.environ.copy())
assert ordered_result.returncode == 0, ordered_result.stderr
assert ordered_log.read_text().splitlines() == ["first", "second", "third"]

failing_commands = [
    "printf 'first\\n' >failure-order.log",
    "printf 'failed\\n' >>failure-order.log\nfalse",
    "printf 'must-not-run\\n' >>failure-order.log",
]
failing_setup = module.build_fail_closed_setup_command(failing_commands)
failing_result = run_polyscope_setup(ordered_root, [failing_setup], os.environ.copy())
assert failing_result.returncode != 0
assert ordered_root.joinpath("failure-order.log").read_text().splitlines() == ["first", "failed"]

# Fully valid candidates retain the generated setup behavior for every managed
# repository after entering the single fail-closed boundary.
for repo_name, generated_spec in generated_specs.items():
    valid_root = workspace / "native setup valid roots with spaces" / repo_name
    write_valid_instructions(valid_root)
    valid_root.joinpath("package.json").write_text(
        json.dumps({"name": f"valid-{repo_name}", "private": True}) + "\n"
    )
    valid_root.joinpath("package-lock.json").write_text(
        json.dumps(
            {
                "name": f"valid-{repo_name}",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {},
            }
        )
        + "\n"
    )
    valid_root.joinpath("composer.json").write_text(
        json.dumps({"name": f"secpal/{repo_name.lower().replace('.', '-')}", "scripts": {}}) + "\n"
    )
    valid_root.joinpath("composer.lock").write_text("{}\n")
    valid_root.joinpath(".env.example").write_text(
        "APP_KEY=base64:test-key\nDB_CONNECTION=sqlite\nDB_DATABASE=database/database.sqlite\n"
    )
    valid_root.joinpath("database").mkdir()

    setup_commands = module.render_local_config(generated_spec)["scripts"]["setup"]
    result = run_polyscope_setup(valid_root, setup_commands, native_env)
    assert result.returncode == 0, (repo_name, result.stdout, result.stderr)

    native_commands = generated_spec[module.NATIVE_SETUP_COMMANDS_KEY]
    command_text = "\n".join(native_commands)
    if "npm " in command_text:
        assert valid_root.joinpath(".native-npm-invoked").is_file(), repo_name
    if "composer " in command_text:
        assert valid_root.joinpath(".native-composer-invoked").is_file(), repo_name
    if "php " in command_text or "--bootstrap-api-worktree" in command_text:
        assert valid_root.joinpath(".native-php-invoked").is_file(), repo_name


# Provisioning must use current active database registrations as its allowlist.
source_workspace = workspace / "source roots"
repo_state: dict[str, dict[str, str]] = {}
for index, repo_name in enumerate(module.REPO_SETTINGS, start=1):
    source_root = source_workspace / repo_name
    write_valid_instructions(source_root)
    repo_state[repo_name] = {
        "id": f"{index:08x}",
        "name": f"SecPal/{repo_name}",
        "path": str(source_root),
    }

github_source = source_workspace / ".github"
github_source.joinpath("package.json").write_text(
    json.dumps(
        {
            "name": "github-test-source",
            "private": True,
            "scripts": {"copilot:review:scan": "true"},
        }
    )
    + "\n"
)
github_source.joinpath("package-lock.json").write_text(
    json.dumps(
        {
            "name": "github-test-source",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {},
        }
    )
    + "\n"
)

repo_specs = module.build_repo_specs(source_workspace)
clone_root = workspace / "clone root with spaces"
github_clone_root = clone_root / repo_state[".github"]["id"]
valid_candidate = github_clone_root / "registered-valid-1a2b3c4d"
invalid_candidate = github_clone_root / "registered-invalid"
unregistered_candidate = github_clone_root / "silent-seal-unregistered"
outside_candidate = workspace / "outside-clone-root"

for candidate in (valid_candidate, invalid_candidate, unregistered_candidate, outside_candidate):
    candidate.joinpath(".git", "info").mkdir(parents=True)
    candidate.joinpath(".git", "hooks").mkdir(parents=True)
    write_valid_instructions(candidate)
    candidate.joinpath("package.json").write_text(
        json.dumps({"name": candidate.name, "private": True}) + "\n"
    )
    candidate.joinpath("package-lock.json").write_text(
        json.dumps(
            {
                "name": candidate.name,
                "lockfileVersion": 3,
                "requires": True,
                "packages": {},
            }
        )
        + "\n"
    )

invalid_candidate.joinpath("AGENTS.md").write_text("# Invalid registered candidate\n")
unregistered_sentinel = unregistered_candidate / "unrelated-sentinel"
unregistered_sentinel.write_bytes(b"unchanged")

fake_bin = workspace / "fake bin"
fake_bin.mkdir()
setup_log = workspace / "setup.log"
fake_npm = fake_bin / "npm"
fake_npm.write_text(
    "#!/usr/bin/env bash\n"
    "printf '%s\\n' \"$PWD:$*\" >>\"$SETUP_LOG\"\n"
    "exit 0\n"
)
fake_npm.chmod(0o755)
test_env = os.environ.copy()
test_env["PATH"] = f"{fake_bin}:{test_env['PATH']}"
test_env["SETUP_LOG"] = str(setup_log)
os.environ.update({"PATH": test_env["PATH"], "SETUP_LOG": str(setup_log)})

db_path = workspace / "polyscope.db"
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
            status text default 'active' not null,
            created_at text default (datetime('now')) not null
        );
        """
    )
    connection.executemany(
        "insert into repositories (id, name, path) values (?, ?, ?)",
        [(entry["id"], entry["name"], entry["path"]) for entry in repo_state.values()],
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
        ("valid", repo_state[".github"]["id"], "valid", str(valid_candidate)),
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'deleted')",
        ("deleted", repo_state[".github"]["id"], "deleted", str(unregistered_candidate)),
    )

provisioned, cleaned, failures = module.provision_worktrees(
    repo_state,
    repo_specs,
    clone_root,
    db_path=db_path,
)
assert provisioned == [".github:registered-valid"], provisioned
assert cleaned == [], cleaned
assert failures == [], failures
assert valid_candidate.joinpath(module.PROVISION_MARKER_FILENAME).is_file()
assert not unregistered_candidate.joinpath(module.PROVISION_MARKER_FILENAME).exists()
assert unregistered_sentinel.read_bytes() == b"unchanged"
assert str(unregistered_candidate) not in setup_log.read_text()
assert unregistered_candidate.is_dir()

# Provisioning must preserve the physical hash directory as the authoritative
# server deletion path. Stable aliases are separately owned and tracked by the
# rollout so they can be removed after the official deletion removes the
# physical target and database registration.
deletion_candidate = github_clone_root / "registered-delete-5e6f7a8b"
deletion_git_source = workspace / "official deletion git source"
deletion_git_source.mkdir()
subprocess.run(["git", "init", "-b", "main", str(deletion_git_source)], check=True, capture_output=True)
write_valid_instructions(deletion_git_source)
deletion_git_source.joinpath("package.json").write_text(
    json.dumps({"name": "registered-delete", "private": True}) + "\n"
)
deletion_git_source.joinpath("package-lock.json").write_text(
    json.dumps(
        {
            "name": "registered-delete",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {},
        }
    )
    + "\n"
)
subprocess.run(["git", "-C", str(deletion_git_source), "add", "."], check=True)
subprocess.run(
    [
        "git",
        "-C",
        str(deletion_git_source),
        "-c",
        "user.name=Package 1 fixture",
        "-c",
        "user.email=package-1-fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "test: seed deletion fixture",
    ],
    check=True,
    capture_output=True,
)
subprocess.run(
    [
        "git",
        "-C",
        str(deletion_git_source),
        "worktree",
        "add",
        "-b",
        "package-1-deletion-fixture",
        str(deletion_candidate),
    ],
    check=True,
    capture_output=True,
)
with sqlite3.connect(db_path) as connection:
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
        ("delete", repo_state[".github"]["id"], "delete", str(deletion_candidate)),
    )
provisioned, cleaned, failures = module.provision_worktrees(
    repo_state,
    repo_specs,
    clone_root,
    db_path=db_path,
)
assert provisioned == [".github:registered-delete"], provisioned
assert cleaned == []
assert failures == []

with sqlite3.connect(db_path) as connection:
    registered_path = connection.execute(
        "select path from worktrees where id = 'delete'"
    ).fetchone()[0]
assert pathlib.Path(registered_path) == deletion_candidate
primary_alias = github_clone_root / "registered-delete"
assert primary_alias.is_symlink()
assert os.readlink(primary_alias) == deletion_candidate.name
assert deletion_candidate.joinpath(module.PROVISION_MARKER_FILENAME).is_file()
deletion_candidate.joinpath("node_modules").mkdir()
deletion_candidate.joinpath("node_modules", "dependency-sentinel").write_text("installed")

source_config_snapshots: dict[pathlib.Path, tuple[bytes, int]] = {}
for source_root_entry in source_workspace.iterdir():
    source_config = source_root_entry / module.POLYSCOPE_LOCAL_CONFIG_NAME
    source_config.write_text('{"sentinel":true}\n')
    source_config_snapshots[source_config] = (
        source_config.read_bytes(),
        source_config.stat().st_mtime_ns,
    )
db_snapshot = (db_path.read_bytes(), db_path.stat().st_mtime_ns)
provisioned, cleaned, failures = module.provision_worktrees(
    repo_state,
    repo_specs,
    clone_root,
    db_path=db_path,
)
assert provisioned == []
assert cleaned == []
assert failures == []
assert (db_path.read_bytes(), db_path.stat().st_mtime_ns) == db_snapshot
for source_config, snapshot in source_config_snapshots.items():
    assert (source_config.read_bytes(), source_config.stat().st_mtime_ns) == snapshot

secondary_alias = github_clone_root / "registered-delete-secondary"
secondary_alias.symlink_to(deletion_candidate.name)
module.record_workspace_alias(secondary_alias, deletion_candidate)
unrelated_alias = github_clone_root / "user-owned-alias"
unrelated_alias.symlink_to(deletion_candidate.name)
assert unrelated_alias.is_symlink()

# Model the official server contract: delete precisely the registered path and
# row, then let the registration-triggered provision reconciliation clean only
# Package-1-owned aliases. This is deliberately not a clone-reaper fixture.
deletion_result = subprocess.run(
    # Polyscope owns the generated local config and provision marker, so its
    # official delete is allowed to remove those untracked lifecycle files.
    ["git", "-C", str(deletion_git_source), "worktree", "remove", "--force", str(registered_path)],
    capture_output=True,
    text=True,
)
assert deletion_result.returncode == 0, (
    deletion_result.stdout,
    deletion_result.stderr,
    subprocess.run(
        ["git", "-C", str(deletion_candidate), "status", "--short", "--ignored"],
        capture_output=True,
        text=True,
    ).stdout,
)
with sqlite3.connect(db_path) as connection:
    connection.execute("delete from worktrees where id = 'delete'")
    assert connection.execute("select count(*) from worktrees where id = 'delete'").fetchone()[0] == 0
removed_aliases = module.cleanup_removed_workspace_aliases(
    repo_state,
    clone_root,
    {repo_name: [] for repo_name in repo_state},
)
assert removed_aliases == sorted([str(primary_alias), str(secondary_alias)])
assert not deletion_candidate.exists()
assert not deletion_candidate.joinpath("node_modules", "dependency-sentinel").exists()
assert not deletion_candidate.joinpath(module.PROVISION_MARKER_FILENAME).exists()
assert str(deletion_candidate) not in subprocess.run(
    ["git", "-C", str(deletion_git_source), "worktree", "list", "--porcelain"],
    check=True,
    capture_output=True,
    text=True,
).stdout
assert not primary_alias.exists() and not primary_alias.is_symlink()
assert not secondary_alias.exists() and not secondary_alias.is_symlink()
assert unrelated_alias.is_symlink(), (
    os.path.lexists(unrelated_alias),
    module.load_workspace_alias_registry(github_clone_root),
    removed_aliases,
)
assert module.load_workspace_alias_registry(github_clone_root) == {
    "registered-valid": valid_candidate.name,
}

# Registration aliases may be migrated back to their verified physical target,
# but symlink chains and paths outside the expected repository clone root are
# never accepted as authoritative deletion identities.
chain_target = github_clone_root / "chain-target-2b3c4d5e"
chain_target.mkdir()
chain_middle = github_clone_root / "chain-middle"
chain_middle.symlink_to(chain_target.name)
chain_alias = github_clone_root / "chain-alias"
chain_alias.symlink_to(chain_middle.name)
with sqlite3.connect(db_path) as connection:
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
        ("chain", repo_state[".github"]["id"], "chain", str(chain_alias)),
    )
try:
    module.preserve_registered_workspace_physical_path(chain_target, db_path=db_path)
except RuntimeError as error:
    assert "direct alias" in str(error).lower() or "symlink" in str(error).lower(), error
else:
    raise AssertionError("symlink-chain registration must fail closed")
with sqlite3.connect(db_path) as connection:
    assert connection.execute("select path from worktrees where id = 'chain'").fetchone()[0] == str(chain_alias)
    connection.execute("delete from worktrees where id = 'chain'")

# Registry records cannot escape the repository clone root or turn another
# user-owned path into an alias-cleanup target.
unsafe_registry_root = clone_root / repo_state["GuardGuide"]["id"]
unsafe_registry_root.mkdir(parents=True)
outside_sentinel = workspace / "outside-alias-sentinel"
outside_sentinel.write_text("unchanged")
module.workspace_alias_registry_path(unsafe_registry_root).write_text(
    json.dumps({"version": 1, "aliases": {"managed": "../outside-alias-sentinel"}}) + "\n"
)
try:
    module.cleanup_removed_workspace_aliases(
        repo_state,
        clone_root,
        {repo_name: [] for repo_name in repo_state},
    )
except RuntimeError as error:
    assert "one path component" in str(error), error
else:
    raise AssertionError("workspace alias registry traversal must fail closed")
assert outside_sentinel.read_text() == "unchanged"

# SQLite URI mode must quote legal filename characters instead of treating
# them as URI query, fragment, or percent-escape syntax and selecting or
# creating a different database.
for index, unsafe_name in enumerate(
    ("polyscope?authoritative.db", "polyscope#authoritative.db", "polyscope%25authoritative.db")
):
    uri_fixture = workspace / f"sqlite-uri-{index}"
    uri_fixture.mkdir()
    uri_db_path = uri_fixture / unsafe_name
    with sqlite3.connect(uri_db_path) as connection:
        connection.execute(
            """
            create table worktrees (
                id text primary key,
                repo_id text not null,
                branch text not null,
                path text not null,
                status text default 'active' not null,
                created_at text default (datetime('now')) not null
            )
            """
        )
        connection.execute(
            "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
            (f"uri-valid-{index}", repo_state[".github"]["id"], "uri-valid", str(valid_candidate)),
        )

    uri_registered = module.load_registered_worktree_paths(uri_db_path, repo_state, clone_root)
    assert uri_registered[".github"] == [valid_candidate.resolve()], uri_registered[".github"]
    assert sorted(uri_fixture.iterdir()) == [uri_db_path]

# Legacy Polyscope databases predate both lifecycle columns. All of their rows
# remain active, and record lookup must fall back to deterministic ID ordering.
legacy_db_path = workspace / "legacy-polyscope.db"
with sqlite3.connect(legacy_db_path) as connection:
    connection.execute(
        """
        create table worktrees (
            id text primary key,
            repo_id text not null,
            branch text not null,
            path text not null
        )
        """
    )
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path) values (?, ?, ?, ?)",
        ("legacy-valid", repo_state[".github"]["id"], "legacy", str(valid_candidate)),
    )

legacy_registered = module.load_registered_worktree_paths(legacy_db_path, repo_state, clone_root)
assert legacy_registered[".github"] == [valid_candidate.resolve()], legacy_registered[".github"]
with sqlite3.connect(legacy_db_path) as connection:
    assert module.find_current_worktree_record(connection, valid_candidate) == (
        "legacy-valid",
        str(valid_candidate),
    )
    resolver_namespace: dict[str, object] = {}
    exec(module.build_linked_workspace_resolver_source(), resolver_namespace)
    previous_cwd = pathlib.Path.cwd()
    os.chdir(valid_candidate)
    try:
        assert resolver_namespace["find_current_worktree"](connection) == (
            "legacy-valid",
            str(valid_candidate),
        )
    finally:
        os.chdir(previous_cwd)

with sqlite3.connect(db_path) as connection:
    connection.execute("delete from worktrees")
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
        ("invalid", repo_state[".github"]["id"], "invalid", str(invalid_candidate)),
    )

log_before = setup_log.read_bytes()
provisioned, cleaned, failures = module.provision_worktrees(
    repo_state,
    repo_specs,
    clone_root,
    db_path=db_path,
)
assert provisioned == [], provisioned
assert cleaned == [], cleaned
assert len(failures) == 1, failures
assert failures[0]["path"] == str(invalid_candidate), failures
assert "canonical AI-instruction validation failed" in failures[0]["error"], failures
assert setup_log.read_bytes() == log_before
assert not invalid_candidate.joinpath(module.PROVISION_MARKER_FILENAME).exists()
assert not unregistered_candidate.joinpath(module.PROVISION_MARKER_FILENAME).exists()

with sqlite3.connect(db_path) as connection:
    connection.execute("delete from worktrees")
    connection.execute(
        "insert into worktrees (id, repo_id, branch, path, status) values (?, ?, ?, ?, 'active')",
        ("outside", repo_state[".github"]["id"], "outside", str(outside_candidate)),
    )

try:
    module.provision_worktrees(repo_state, repo_specs, clone_root, db_path=db_path)
except (RuntimeError, SystemExit, ValueError) as error:
    assert "outside" in str(error).lower() or "clone root" in str(error).lower(), error
else:
    raise AssertionError("registered path outside clone root must fail closed")

print("Package-1 setup-order and registered-worktree tests passed.")
PY
