#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run_git(repo_path: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.rstrip("\n")


def assert_managed_hook_is_retired(module: Any, worktree_path: Path, hooks_dir: Path) -> None:
    managed_target = worktree_path / "scripts" / "preflight.sh"
    managed_target.parent.mkdir(parents=True, exist_ok=True)
    managed_target.touch()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-push"
    hook_path.symlink_to(managed_target)

    module.remove_managed_pre_push_hook(worktree_path)

    assert not hook_path.is_symlink(), hook_path


def assert_active_pre_commit_hook_is_respected(
    module: Any,
    worktree_path: Path,
    hooks_dir: Path,
    fake_pre_commit: Path,
    invocation_marker: Path,
) -> None:
    (worktree_path / ".pre-commit-config.yaml").touch()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"
    hook_path.touch()
    invocation_marker.unlink(missing_ok=True)

    original_resolve_executable = module.resolve_executable
    module.resolve_executable = lambda name: (
        fake_pre_commit if name == "pre-commit" else original_resolve_executable(name)
    )
    try:
        module.ensure_pre_commit_hook(worktree_path)
    finally:
        module.resolve_executable = original_resolve_executable

    assert not invocation_marker.exists(), invocation_marker


def assert_commit_msg_hook_uses_active_directory(
    module: Any,
    worktree_path: Path,
    hooks_dir: Path,
) -> None:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "commit-msg"
    hook_path.unlink(missing_ok=True)

    module.ensure_commit_msg_hook(worktree_path)

    assert hook_path.is_symlink(), hook_path
    assert hook_path.resolve() == (Path(module.__file__).parent / "strip-ai-trailers.sh").resolve()


def main() -> None:
    script_path = Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location("polyscope_rollout", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        non_repository_path = temporary_root / "not-a-repository"
        non_repository_path.mkdir()
        try:
            module.resolve_git_hooks_dir(non_repository_path)
        except RuntimeError as error:
            assert "unable to resolve active Git hooks" in str(error)
        else:
            raise AssertionError("hook resolution must fail closed outside a Git repository")

        repository_path = temporary_root / "repository"
        linked_worktree_path = temporary_root / "linked-worktree"
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch=main", str(repository_path)],
            check=True,
        )
        run_git(repository_path, "config", "user.email", "tests@example.com")
        run_git(repository_path, "config", "user.name", "SecPal Tests")
        (repository_path / "tracked.txt").touch()
        run_git(repository_path, "add", "tracked.txt")
        run_git(repository_path, "commit", "--quiet", "-m", "fixture")
        run_git(
            repository_path,
            "worktree",
            "add",
            "--quiet",
            "-b",
            "linked",
            str(linked_worktree_path),
        )

        active_hooks_dir = Path(
            run_git(
                linked_worktree_path,
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                "hooks",
            )
        )
        administrative_hooks_dir = module.resolve_git_dir(linked_worktree_path) / "hooks"
        assert active_hooks_dir != administrative_hooks_dir
        assert_managed_hook_is_retired(module, linked_worktree_path, active_hooks_dir)

        invocation_marker = temporary_root / "pre-commit-invoked"
        fake_pre_commit = temporary_root / "pre-commit"
        fake_pre_commit.write_text(
            f"#!/usr/bin/env bash\ntouch {invocation_marker}\n",
            encoding="utf-8",
        )
        fake_pre_commit.chmod(0o755)
        assert_active_pre_commit_hook_is_respected(
            module,
            linked_worktree_path,
            active_hooks_dir,
            fake_pre_commit,
            invocation_marker,
        )
        assert_commit_msg_hook_uses_active_directory(
            module,
            linked_worktree_path,
            active_hooks_dir,
        )

        primary_managed_target = repository_path / "scripts" / "preflight.sh"
        primary_managed_target.parent.mkdir(parents=True)
        primary_managed_target.touch()
        primary_managed_hook = active_hooks_dir / "pre-push"
        primary_managed_hook.symlink_to(primary_managed_target)
        module.remove_managed_pre_push_hook(linked_worktree_path)
        assert not primary_managed_hook.is_symlink(), primary_managed_hook

        custom_target = linked_worktree_path / "scripts" / "custom-pre-push.sh"
        custom_target.touch()
        custom_hook = active_hooks_dir / "pre-push"
        custom_hook.symlink_to(custom_target)
        module.remove_managed_pre_push_hook(linked_worktree_path)
        assert custom_hook.resolve() == custom_target.resolve()
        custom_hook.unlink()

        for configured_hooks_path in (
            temporary_root / "shared hooks ",
            Path(".git-hooks"),
        ):
            run_git(
                linked_worktree_path,
                "config",
                "core.hooksPath",
                str(configured_hooks_path),
            )
            configured_hooks_dir = Path(
                run_git(
                    linked_worktree_path,
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-path",
                    "hooks",
                )
            )
            assert_managed_hook_is_retired(module, linked_worktree_path, configured_hooks_dir)
            assert_active_pre_commit_hook_is_respected(
                module,
                linked_worktree_path,
                configured_hooks_dir,
                fake_pre_commit,
                invocation_marker,
            )
            assert_commit_msg_hook_uses_active_directory(
                module,
                linked_worktree_path,
                configured_hooks_dir,
            )


if __name__ == "__main__":
    main()
