#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main, mock


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLLOUT_SCRIPT = REPO_ROOT / "scripts/polyscope-rollout.py"


def load_rollout_module():
    spec = importlib.util.spec_from_file_location("polyscope_rollout_followups", ROLLOUT_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load rollout script at {ROLLOUT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rollout = load_rollout_module()


class PolyscopeRolloutFollowupTests(TestCase):
    def test_api_health_probe_stays_unsuccessful_while_provisioning(self) -> None:
        repo_state = {
            "api": {"id": "api-id"},
            "frontend": {"id": "frontend-id"},
            "GuardGuide": {"id": "guardguide-id"},
            "secpal.app": {"id": "secpal-app-id"},
            "guardguide.de": {"id": "guardguide-de-id"},
        }

        rendered = rollout.render_nginx_config(repo_state)

        self.assertIn("location = /health/ready {", rendered)
        health_location = rendered.split("location = /health/ready {", 1)[1].split("}", 1)[0]
        self.assertIn("return 503;", health_location)

    def test_pending_api_storage_reset_bypasses_matching_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            clone_root = root / "clones"
            worktree = clone_root / "api-id" / "mighty-hyena-1c04a2fb"
            worktree.mkdir(parents=True)
            (worktree / ".env").write_text(
                f"{rollout.PREVIEW_STORAGE_RESET_REQUIRED_ENV_KEY}=1\n"
            )
            bootstrap = mock.Mock(return_value=(True, "database:secpal__preview__mighty_hyena"))

            with mock.patch.multiple(
                rollout,
                load_registered_worktree_paths=mock.Mock(
                    return_value={"api": [worktree]}
                ),
                revoke_unregistered_preview_nginx_access=mock.Mock(),
                is_provisionable_worktree=mock.Mock(return_value=True),
                cleanup_removed_workspace_aliases=mock.Mock(return_value=[]),
                cleanup_removed_api_preview_databases=mock.Mock(return_value=[]),
                preserve_registered_workspace_physical_path=mock.Mock(),
                render_worktree_local_config=mock.Mock(return_value="{}\n"),
                sync_worktree_local_config=mock.Mock(),
                ensure_workspace_alias=mock.Mock(),
                sync_worktree_auxiliary_files=mock.Mock(),
                ensure_worktree_hooks=mock.Mock(),
                acquire_api_worktree_bootstrap_lock=mock.Mock(
                    side_effect=lambda path: contextlib.nullcontext(path)
                ),
                collect_linked_setup_context=mock.Mock(return_value={}),
                resolve_current_workspace_name=mock.Mock(return_value="mighty-hyena"),
                build_setup_hash=mock.Mock(return_value="setup-hash"),
                ensure_api_worktree_ready=mock.Mock(
                    return_value=(True, "database:secpal__preview__mighty_hyena")
                ),
                load_provision_marker=mock.Mock(
                    return_value={
                        "setup_hash": "setup-hash",
                        "preview_storage_target": "database:secpal__preview__mighty_hyena",
                    }
                ),
                _bootstrap_api_worktree_locked=bootstrap,
                ensure_preview_nginx_access=mock.Mock(),
                write_provision_marker=mock.Mock(),
            ):
                provisioned, _cleaned, failures = rollout.provision_worktrees(
                    {"api": {"id": "api-id"}},
                    {
                        "api": {
                            rollout.NATIVE_SETUP_COMMANDS_KEY: ["bootstrap-api"],
                            "path": root / "source-api",
                            "preview_prefix": "api",
                        }
                    },
                    clone_root,
                    db_path=root / "polyscope.db",
                )

            bootstrap.assert_called_once()
            self.assertEqual(provisioned, ["api:mighty-hyena"])
            self.assertEqual(failures, [])

    def test_exported_nginx_config_uses_post_provision_redirects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            alias_created = False

            def provision(*_args, **_kwargs):
                nonlocal alias_created
                alias_created = True
                return [], [], []

            def redirects(*_args, **_kwargs):
                if not alias_created:
                    return {}
                return {"frontend": {"mighty-hyena-1c04a2fb": "mighty-hyena"}}

            args = SimpleNamespace(
                clone_root=root / "clones",
                db_path=root / "polyscope.db",
                install_nginx=False,
                refresh_nginx=False,
                nginx_http2_syntax="modern",
                nginx_output=root / "preview.nginx.conf",
                polyscope_api_base="http://127.0.0.1:4321/api",
                provision_worktrees=True,
                repo_state_file=root / "repo-state.json",
                skip_db_sync=True,
                skip_local_configs=True,
                summary_output=None,
                workspace_root=root / "workspace",
            )
            args.clone_root.mkdir()

            with mock.patch.multiple(
                rollout,
                build_repo_specs=mock.Mock(return_value={}),
                validate_repo_instruction_files=mock.Mock(),
                validate_repo_local_configs=mock.Mock(),
                load_repo_state=mock.Mock(return_value={}),
                build_preview_workspace_redirects=mock.Mock(side_effect=redirects),
                render_nginx_config=mock.Mock(
                    side_effect=lambda *_args, **kwargs: json.dumps(
                        kwargs["workspace_redirects"], sort_keys=True
                    )
                    + "\n"
                ),
                provision_worktrees=mock.Mock(side_effect=provision),
            ):
                self.assertEqual(rollout.run_rollout(args), 0)

            exported = json.loads(args.nginx_output.read_text())
            self.assertEqual(
                exported,
                {"frontend": {"mighty-hyena-1c04a2fb": "mighty-hyena"}},
            )

    def test_install_validates_redirects_before_mutating_preview_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            revoke_access = mock.Mock()
            provision = mock.Mock(return_value=([], [], []))
            args = SimpleNamespace(
                clone_root=root / "clones",
                db_path=root / "polyscope.db",
                install_nginx=True,
                refresh_nginx=False,
                nginx_http2_syntax="modern",
                nginx_output=root / "preview.nginx.conf",
                polyscope_api_base="http://127.0.0.1:4321/api",
                provision_worktrees=True,
                repo_state_file=root / "repo-state.json",
                skip_db_sync=True,
                skip_local_configs=True,
                summary_output=None,
                workspace_root=root / "workspace",
            )

            with mock.patch.multiple(
                rollout,
                build_repo_specs=mock.Mock(return_value={}),
                validate_repo_instruction_files=mock.Mock(),
                validate_repo_local_configs=mock.Mock(),
                load_repo_state=mock.Mock(return_value={}),
                detect_nginx_http2_syntax=mock.Mock(return_value="modern"),
                revoke_all_preview_nginx_access=revoke_access,
                provision_worktrees=provision,
                build_preview_workspace_redirects=mock.Mock(
                    side_effect=RuntimeError("invalid workspace alias registry")
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "invalid workspace alias registry"
                ):
                    rollout.run_rollout(args)

            revoke_access.assert_not_called()
            provision.assert_not_called()

    def test_install_validates_nginx_output_before_mutating_preview_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            revoke_access = mock.Mock()
            provision = mock.Mock(return_value=([], [], []))
            args = SimpleNamespace(
                clone_root=root / "clones",
                db_path=root / "polyscope.db",
                install_nginx=True,
                refresh_nginx=False,
                nginx_http2_syntax="modern",
                nginx_output=root / "missing" / "preview.nginx.conf",
                polyscope_api_base="http://127.0.0.1:4321/api",
                provision_worktrees=True,
                repo_state_file=root / "repo-state.json",
                skip_db_sync=True,
                skip_local_configs=True,
                summary_output=None,
                workspace_root=root / "workspace",
            )

            with mock.patch.multiple(
                rollout,
                build_repo_specs=mock.Mock(return_value={}),
                validate_repo_instruction_files=mock.Mock(),
                validate_repo_local_configs=mock.Mock(),
                load_repo_state=mock.Mock(return_value={}),
                detect_nginx_http2_syntax=mock.Mock(return_value="modern"),
                revoke_all_preview_nginx_access=revoke_access,
                provision_worktrees=provision,
                build_preview_workspace_redirects=mock.Mock(return_value={}),
                render_nginx_config=mock.Mock(return_value="valid nginx\n"),
            ):
                with self.assertRaises(FileNotFoundError):
                    rollout.run_rollout(args)

            revoke_access.assert_not_called()
            provision.assert_not_called()


if __name__ == "__main__":
    main()
