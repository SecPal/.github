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
import sqlite3
import subprocess
import sys

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


def run_setup_sequence(root: pathlib.Path, commands: list[str], env: dict[str, str]) -> None:
    for command in commands:
        subprocess.run(
            ["bash", "-c", "set -euo pipefail; " + command],
            cwd=root,
            env=env,
            check=True,
        )


# Every generated native setup must enter the real canonical validator before
# any repository-specific mutation. Execute that boundary rather than merely
# inspecting source ordering.
native_source_workspace = workspace / "native source roots"
for repo_name in module.REPO_SETTINGS:
    write_valid_instructions(native_source_workspace / repo_name)
generated_specs = module.build_repo_specs(native_source_workspace)
side_effect_script = (
    "from pathlib import Path; "
    "Path('.env').write_text('mutated\\n'); "
    "Path('node_modules').mkdir(); "
    "Path('vendor').mkdir(); "
    "Path('database.sqlite').write_text('mutated'); "
    "Path('.setup-side-effect').write_text('ran'); "
    "Path('.polyscope-secpal-provisioned.json').write_text('{}')"
)
side_effect_command = f"python3 -c {shlex.quote(side_effect_script)}"

for repo_name, generated_spec in generated_specs.items():
    setup_commands = module.render_local_config(generated_spec).get("scripts", {}).get("setup", [])
    assert setup_commands, repo_name
    validation_command = setup_commands[0]
    assert "--validate-instruction-worktree" in validation_command, (repo_name, validation_command)

    invalid_root = workspace / "native setup ; invalid roots" / repo_name
    write_valid_instructions(invalid_root)
    invalid_root.joinpath("AGENTS.md").write_text("# Missing SPDX metadata\n")
    unrelated = invalid_root / "unrelated-sentinel"
    unrelated.write_bytes(b"unchanged")
    try:
        run_setup_sequence(invalid_root, [validation_command, side_effect_command], os.environ.copy())
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError(f"invalid {repo_name} instructions reached native setup")

    for forbidden in (
        ".env",
        "node_modules",
        "vendor",
        "database.sqlite",
        ".setup-side-effect",
        ".polyscope-secpal-provisioned.json",
    ):
        assert not invalid_root.joinpath(forbidden).exists(), (repo_name, forbidden)
    assert unrelated.read_bytes() == b"unchanged"

valid_root = workspace / "native setup valid root with spaces"
write_valid_instructions(valid_root)
valid_validation_command = module.render_local_config(generated_specs[".github"])["scripts"]["setup"][0]
run_setup_sequence(valid_root, [valid_validation_command, side_effect_command], os.environ.copy())
assert valid_root.joinpath(".setup-side-effect").read_text() == "ran"


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
valid_candidate = github_clone_root / "registered-valid"
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
