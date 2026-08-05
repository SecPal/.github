#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import ast
import contextlib
import importlib.util
import inspect
import io
import json
import subprocess
import tempfile
import tokenize
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
    def test_user_server_startup_uses_lightweight_nginx_convergence(self) -> None:
        installer = (REPO_ROOT / "scripts/install-polyscope-rollout.sh").read_text()
        ready_command = next(
            line
            for line in installer.splitlines()
            if line.startswith("ROLLOUT_READY_COMMAND=")
        )

        for argument in (
            "--nginx-manifest-output $POLYSCOPE_NGINX_MANIFEST",
            "--skip-local-configs",
            "--skip-db-sync",
            "--refresh-nginx",
            "--skip-if-provision-locked",
        ):
            self.assertIn(argument, ready_command)

    def test_user_server_startup_receives_the_validated_sudo_binary(self) -> None:
        installer = (REPO_ROOT / "scripts/install-polyscope-rollout.sh").read_text()
        server_unit = installer.split('cat >"$SERVER_UNIT" <<EOF', 1)[1].split("EOF", 1)[0]

        self.assertIn("Environment=POLYSCOPE_SUDO_BIN=$SUDO_BIN", server_unit)

    def test_system_server_startup_skips_refresh_while_provisioning(self) -> None:
        installer = (REPO_ROOT / "scripts/install-polyscope-system-components.sh").read_text()
        system_dropin = installer.split('cat >"$TEMP_DIR/zz-secpal-runtime.conf" <<EOF', 1)[
            1
        ].split("EOF", 1)[0]

        self.assertIn("--refresh-nginx --skip-if-provision-locked", system_dropin)

    def test_provision_service_allows_the_scheduler_gate_to_finish(self) -> None:
        installer = (REPO_ROOT / "scripts/install-polyscope-rollout.sh").read_text()
        provision_unit = installer.split('cat >"$PROVISION_SERVICE_UNIT" <<EOF', 1)[1].split(
            "EOF", 1
        )[0]

        self.assertIn("TimeoutStartSec=15min", provision_unit)

    def test_nonblocking_provision_lock_reports_contention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock_path = Path(temporary_directory) / "provision.lock"

            with rollout.provision_worktree_lock(lock_path) as acquired:
                self.assertTrue(acquired)
                with rollout.provision_worktree_lock(lock_path, blocking=False) as acquired_again:
                    self.assertFalse(acquired_again)

    def test_startup_refresh_skips_cleanly_when_provisioning_holds_the_lock(self) -> None:
        args = SimpleNamespace(
            install_nginx=False,
            provision_lock_path=Path("/tmp/provision.lock"),
            provision_worktrees=False,
            refresh_nginx=True,
            skip_if_provision_locked=True,
        )
        run_rollout = mock.Mock(return_value=0)

        @contextlib.contextmanager
        def contended_lock(_path, *, blocking=True):
            self.assertFalse(blocking)
            yield False

        with mock.patch.multiple(
            rollout,
            parse_args=mock.Mock(return_value=args),
            dispatch_validation_only_direct_mode=mock.Mock(return_value=None),
            dispatch_instruction_dependent_direct_api_mode=mock.Mock(return_value=None),
            provision_worktree_lock=contended_lock,
            run_rollout=run_rollout,
        ):
            self.assertEqual(rollout.main(), 0)

        run_rollout.assert_not_called()

    def test_preview_api_environment_enables_complete_public_bootstrap(self) -> None:
        updates = rollout.build_api_preview_env_updates("mighty-hyena")

        self.assertEqual(updates["BOOTSTRAP_PUBLIC_ENABLED"], "true")
        self.assertEqual(
            updates["BOOTSTRAP_INSTANCE_DISPLAY_NAME"],
            "SecPal Preview (mighty-hyena)",
        )
        self.assertEqual(updates["BOOTSTRAP_MINIMUM_SUPPORTED_APP_VERSION"], "1.4.0")
        self.assertEqual(updates["BOOTSTRAP_MINIMUM_SUPPORTED_APP_BUILD"], "10400")

    def test_nginx_manifest_is_not_replaced_by_an_incompatible_helper(self) -> None:
        writer = mock.Mock()
        helper = mock.Mock(
            return_value=SimpleNamespace(
                returncode=0,
                stdout="Polyscope nginx helper check passed\n",
                stderr="",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "manifest schema 2"):
            rollout.write_compatible_nginx_manifest(
                Path("/home/secpal/.local/state/polyscope/nginx-manifest.json"),
                {"version": 2},
                writer=writer,
                helper_runner=helper,
                service_user=SimpleNamespace(pw_uid=0, pw_gid=0),
            )

        writer.assert_not_called()

    def test_nginx_compatibility_check_ignores_environment_helper_override(self) -> None:
        fixed_helper = Path("/usr/local/libexec/reviewed-nginx-helper")
        helper = mock.Mock(
            return_value=SimpleNamespace(
                returncode=0,
                stdout="Polyscope nginx helper check passed manifest_schema=2\n",
                stderr="",
            )
        )

        with (
            mock.patch.object(rollout, "DEFAULT_NGINX_HELPER_PATH", fixed_helper),
            mock.patch.object(rollout.os, "geteuid", return_value=1000),
            mock.patch.dict(
                rollout.os.environ,
                {"POLYSCOPE_NGINX_HELPER": "/tmp/unreviewed-nginx-helper"},
            ),
        ):
            rollout.check_nginx_helper_compatibility(2, helper_runner=helper)

        command = helper.call_args.args[0]
        self.assertEqual(command[:3], ["sudo", "-k", "-n"])
        self.assertEqual(command[-2:], [str(fixed_helper), "--check"])
        self.assertNotIn("/tmp/unreviewed-nginx-helper", command)

    def test_api_runtime_units_are_persistent_and_contain_no_environment_secrets(self) -> None:
        worktree = Path("/home/secpal/.polyscope/clones/api-id/mighty-hyena-1c04a2fb")
        source = Path("/home/secpal/code/SecPal/api")

        units = rollout.build_api_runtime_unit_specs(
            worktree,
            source,
            workspace="mighty-hyena",
            runtime_revision="a" * 64,
            service_path="/opt/pinned-node/bin:/usr/bin",
        )

        self.assertEqual(len(units), 2)
        rendered = "\n".join(units.values())
        self.assertIn("Restart=on-failure", rendered)
        self.assertIn(f"ConditionPathIsDirectory={worktree}", rendered)
        self.assertIn("--run-api-worktree", rendered)
        self.assertIn("php artisan schedule:work", rendered)
        self.assertIn("php artisan queue:work", rendered)
        self.assertIn("RuntimeRevision=" + "a" * 64, rendered)
        self.assertIn("Environment=PATH=/opt/pinned-node/bin:/usr/bin", rendered)
        self.assertNotIn("DB_PASSWORD", rendered)
        self.assertNotIn("EnvironmentFile=", rendered)

    def test_api_runtime_actions_are_not_autostarted_by_polyscope(self) -> None:
        api_run_actions = rollout.REPO_SETTINGS["api"]["local_config"]["scripts"]["run"]

        for label in ("Queue Worker", "Scheduler"):
            action = next(item for item in api_run_actions if item["label"] == label)
            self.assertFalse(action.get("autostart", False), action)

    def test_api_runtime_revision_changes_with_code_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            worktree = root / "worktree"
            source = root / "source"
            worktree.mkdir()
            source.mkdir()
            (worktree / "app.php").write_text("first\n")
            (worktree / ".env").write_text("APP_ENV=local\n")
            (source / ".env").write_text("DB_PASSWORD=first\n")
            subprocess.run(["git", "init", "-q"], cwd=worktree, check=True)
            subprocess.run(["git", "add", "app.php"], cwd=worktree, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=SecPal Test",
                    "-c",
                    "user.email=test@secpal.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    "Initial fixture",
                ],
                cwd=worktree,
                check=True,
            )

            initial = rollout.build_api_runtime_revision(worktree, source)
            (worktree / "app.php").write_text("second\n")
            code_changed = rollout.build_api_runtime_revision(worktree, source)
            (source / ".env").write_text("DB_PASSWORD=second\n")
            environment_changed = rollout.build_api_runtime_revision(worktree, source)

            self.assertNotEqual(initial, code_changed)
            self.assertNotEqual(code_changed, environment_changed)

    def test_api_runtime_reconciliation_removes_stale_units_and_starts_desired_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            stale_unit = unit_directory / "polyscope-api-worktree-stale-scheduler.service"
            stale_unit.write_text("stale\n")
            stale_target = unit_directory / "stale-target"
            stale_target.write_text("must survive\n")
            stale_link = unit_directory / "polyscope-api-worktree-stale-queue.service"
            stale_link.symlink_to(stale_target)
            desired_target = unit_directory / "desired-target"
            desired_target.write_text("scheduler\n")
            desired_link = unit_directory / "polyscope-api-worktree-mighty-hyena-scheduler.service"
            desired_link.symlink_to(desired_target)
            desired = {
                "polyscope-api-worktree-mighty-hyena-scheduler.service": "scheduler\n",
                "polyscope-api-worktree-mighty-hyena-queue.service": "queue\n",
            }
            systemctl = mock.Mock()

            rollout.reconcile_api_runtime_units(
                desired,
                unit_directory=unit_directory,
                systemctl_runner=systemctl,
            )

            self.assertFalse(stale_unit.exists())
            self.assertFalse(stale_link.exists())
            self.assertTrue(stale_target.exists())
            for unit_name, content in desired.items():
                self.assertEqual((unit_directory / unit_name).read_text(), content)
                self.assertFalse((unit_directory / unit_name).is_symlink())
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", stale_unit.name],
                commands,
            )
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", stale_link.name],
                commands,
            )
            self.assertIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertIn(
                [
                    "systemctl",
                    "--user",
                    "enable",
                    *sorted(desired),
                ],
                commands,
            )
            self.assertIn(
                ["systemctl", "--user", "restart", *sorted(desired)],
                commands,
            )

    def test_api_runtime_reconciliation_does_not_restart_unchanged_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            unit_name = "polyscope-api-worktree-mighty-hyena-scheduler.service"
            content = "scheduler\n"
            unit_path = unit_directory / unit_name
            unit_path.write_text(content)
            unit_path.chmod(0o644)
            systemctl = mock.Mock()

            rollout.reconcile_api_runtime_units(
                {unit_name: content},
                unit_directory=unit_directory,
                systemctl_runner=systemctl,
                prune=False,
            )

            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertNotIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertNotIn(["systemctl", "--user", "restart", unit_name], commands)
            self.assertIn(["systemctl", "--user", "enable", unit_name], commands)
            self.assertIn(["systemctl", "--user", "start", unit_name], commands)

    def test_api_runtime_reconciliation_preserves_a_unit_when_stop_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            stale_unit = unit_directory / "polyscope-api-worktree-stale-scheduler.service"
            stale_unit.write_text("stale\n")
            systemctl = mock.Mock(
                side_effect=subprocess.CalledProcessError(
                    1,
                    ["systemctl", "--user", "disable", "--now", stale_unit.name],
                )
            )

            with self.assertRaisesRegex(RuntimeError, stale_unit.name):
                rollout.reconcile_api_runtime_units(
                    {},
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                )

            self.assertTrue(stale_unit.exists())

    def test_api_runtime_reconciliation_continues_pruning_after_stop_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            failed_unit = unit_directory / "polyscope-api-worktree-aaa-scheduler.service"
            later_unit = unit_directory / "polyscope-api-worktree-zzz-scheduler.service"
            failed_unit.write_text("failed\n")
            later_unit.write_text("later\n")

            def run_systemctl(command, **_kwargs):
                if command[-1] == failed_unit.name:
                    raise subprocess.CalledProcessError(1, command)
                return SimpleNamespace(returncode=0)

            systemctl = mock.Mock(side_effect=run_systemctl)

            with self.assertRaisesRegex(RuntimeError, failed_unit.name):
                rollout.reconcile_api_runtime_units(
                    {},
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                )

            self.assertTrue(failed_unit.exists())
            self.assertFalse(later_unit.exists())
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", failed_unit.name],
                commands,
            )
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", later_unit.name],
                commands,
            )

    def test_api_runtime_reconciliation_continues_pruning_after_unlink_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            failed_unit = unit_directory / "polyscope-api-worktree-aaa-scheduler.service"
            later_unit = unit_directory / "polyscope-api-worktree-zzz-scheduler.service"
            failed_unit.write_text("failed\n")
            later_unit.write_text("later\n")
            systemctl = mock.Mock(return_value=SimpleNamespace(returncode=0))
            original_unlink = Path.unlink

            def unlink(path, *args, **kwargs):
                if path == failed_unit:
                    raise OSError("simulated unit removal failure")
                return original_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "unlink", new=unlink),
                self.assertRaisesRegex(RuntimeError, failed_unit.name),
            ):
                rollout.reconcile_api_runtime_units(
                    {},
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                )

            self.assertTrue(failed_unit.exists())
            self.assertFalse(later_unit.exists())
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", failed_unit.name],
                commands,
            )
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", later_unit.name],
                commands,
            )

    def test_api_runtime_reconciliation_validates_desired_names_before_pruning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            stale_unit = unit_directory / "polyscope-api-worktree-stale-scheduler.service"
            stale_unit.write_text("stale\n")
            systemctl = mock.Mock()

            with self.assertRaisesRegex(ValueError, "unsafe API runtime unit name"):
                rollout.reconcile_api_runtime_units(
                    {"unmanaged.service": "unsafe\n"},
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                )

            self.assertTrue(stale_unit.exists())
            systemctl.assert_not_called()

    def test_api_runtime_reconciliation_replaces_non_utf8_desired_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            unit_name = "polyscope-api-worktree-mighty-hyena-scheduler.service"
            unit_path = unit_directory / unit_name
            unit_path.write_bytes(b"\xff\xfe")
            systemctl = mock.Mock()

            rollout.reconcile_api_runtime_units(
                {unit_name: "desired\n"},
                unit_directory=unit_directory,
                systemctl_runner=systemctl,
                prune=False,
            )

            self.assertEqual(unit_path.read_text(), "desired\n")
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertIn(["systemctl", "--user", "restart", unit_name], commands)

    def test_api_runtime_reconciliation_restores_desired_unit_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            unit_name = "polyscope-api-worktree-mighty-hyena-scheduler.service"
            unit_path = unit_directory / unit_name
            unit_path.write_text("desired\n")
            unit_path.chmod(0o600)
            systemctl = mock.Mock()

            rollout.reconcile_api_runtime_units(
                {unit_name: "desired\n"},
                unit_directory=unit_directory,
                systemctl_runner=systemctl,
                prune=False,
            )

            self.assertEqual(unit_path.stat().st_mode & 0o777, 0o644)
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertIn(["systemctl", "--user", "restart", unit_name], commands)

    def test_api_runtime_reconciliation_restores_desired_unit_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            unit_name = "polyscope-api-worktree-mighty-hyena-scheduler.service"
            unit_path = unit_directory / unit_name
            unit_path.write_text("desired\n")
            unit_path.chmod(0o644)
            systemctl = mock.Mock()
            original_lstat = Path.lstat

            def lstat(path):
                metadata = original_lstat(path)
                if path == unit_path:
                    return SimpleNamespace(
                        st_mode=metadata.st_mode,
                        st_uid=rollout.os.geteuid() + 1,
                    )
                return metadata

            with mock.patch.object(Path, "lstat", new=lstat):
                rollout.reconcile_api_runtime_units(
                    {unit_name: "desired\n"},
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                    prune=False,
                )

            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertIn(["systemctl", "--user", "daemon-reload"], commands)
            self.assertIn(["systemctl", "--user", "restart", unit_name], commands)

    def test_api_runtime_reconciliation_has_no_empty_exception_handler(self) -> None:
        source = inspect.getsource(rollout.reconcile_api_runtime_units)
        tree = compile(source, "reconcile_api_runtime_units", "exec", ast.PyCF_ONLY_AST)
        empty_handlers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and len(node.body) == 1
            and isinstance(node.body[0], ast.Pass)
        ]

        self.assertEqual(empty_handlers, [])

    def test_api_runtime_reconciliation_reports_prune_and_activation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            unit_directory = Path(temporary_directory)
            stale_unit = unit_directory / "polyscope-api-worktree-stale-scheduler.service"
            stale_unit.write_text("stale\n")
            desired_name = "polyscope-api-worktree-mighty-hyena-scheduler.service"

            def run_systemctl(command, **_kwargs):
                if command[-1] == stale_unit.name:
                    raise subprocess.CalledProcessError(1, command)
                if command[-1] == "daemon-reload":
                    raise subprocess.CalledProcessError(1, command)
                return SimpleNamespace(returncode=0)

            with self.assertRaisesRegex(
                RuntimeError,
                f"{stale_unit.name}.*daemon-reload",
            ):
                rollout.reconcile_api_runtime_units(
                    {desired_name: "desired\n"},
                    unit_directory=unit_directory,
                    systemctl_runner=run_systemctl,
                )

    def test_scheduler_failure_revokes_existing_preview_access(self) -> None:
        worktree = Path("/home/secpal/.polyscope/clones/api-id/mighty-hyena-1c04a2fb")
        clone_root = worktree.parents[1]
        source = Path("/home/secpal/code/SecPal/api")
        deny_access = mock.Mock()

        with (
            mock.patch.object(
                rollout,
                "wait_for_api_scheduler_readiness",
                side_effect=RuntimeError("scheduler heartbeat missing"),
            ),
            mock.patch.object(rollout, "deny_preview_nginx_access", new=deny_access),
            self.assertRaisesRegex(RuntimeError, "scheduler heartbeat missing"),
        ):
            rollout.wait_for_api_scheduler_readiness_or_revoke_access(
                clone_root,
                worktree,
                source,
                preview_enabled=True,
            )

        deny_access.assert_called_once_with(clone_root, worktree)

    def test_scheduler_failure_reports_preview_revocation_failure(self) -> None:
        worktree = Path("/home/secpal/.polyscope/clones/api-id/mighty-hyena-1c04a2fb")
        clone_root = worktree.parents[1]
        source = Path("/home/secpal/code/SecPal/api")

        with (
            mock.patch.object(
                rollout,
                "wait_for_api_scheduler_readiness",
                side_effect=RuntimeError("scheduler heartbeat missing"),
            ),
            mock.patch.object(
                rollout,
                "deny_preview_nginx_access",
                side_effect=RuntimeError("ACL update failed"),
            ),
            self.assertRaisesRegex(
                RuntimeError,
                "scheduler heartbeat missing; additionally failed to revoke preview access: ACL update failed",
            ),
        ):
            rollout.wait_for_api_scheduler_readiness_or_revoke_access(
                clone_root,
                worktree,
                source,
                preview_enabled=True,
            )

    def test_canonical_validation_failure_still_prunes_removed_api_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            clone_root = root / "clones"
            worktree = clone_root / "api-id" / "mighty-hyena-1c04a2fb"
            worktree.mkdir(parents=True)
            runtime_id = rollout.build_api_runtime_id(worktree)
            unit_directory = root / "units"
            unit_directory.mkdir()
            registered_unit = unit_directory / (
                f"polyscope-api-worktree-mighty-hyena-{runtime_id}-scheduler.service"
            )
            removed_unit = unit_directory / (
                "polyscope-api-worktree-removed-workspace-bbbbbbbbbbbb-scheduler.service"
            )
            registered_unit.write_text("registered\n")
            removed_unit.write_text("removed\n")
            systemctl = mock.Mock()
            reconcile_runtime_units = rollout.reconcile_api_runtime_units

            def reconcile(desired_units, **kwargs):
                reconcile_runtime_units(
                    desired_units,
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                    **kwargs,
                )

            with mock.patch.multiple(
                rollout,
                should_manage_api_runtime_units=mock.Mock(return_value=True),
                load_registered_worktree_paths=mock.Mock(return_value={"api": [worktree]}),
                revoke_unregistered_preview_nginx_access=mock.Mock(),
                is_provisionable_worktree=mock.Mock(
                    side_effect=rollout.CanonicalInstructionValidationError(
                        "invalid canonical instructions"
                    )
                ),
                reconcile_api_runtime_units=mock.Mock(side_effect=reconcile),
            ):
                _provisioned, _cleaned, failures = rollout.provision_worktrees(
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

            self.assertEqual(len(failures), 1)
            self.assertIn("invalid canonical instructions", failures[0]["error"])
            self.assertTrue(registered_unit.exists())
            self.assertFalse(removed_unit.exists())

    def test_api_runtime_failure_preserves_only_the_registered_runtime_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            clone_root = root / "clones"
            worktree = clone_root / "api-id" / "mighty-hyena-1c04a2fb"
            worktree.mkdir(parents=True)
            (worktree / ".env").write_text("")
            runtime_id = rollout.hashlib.sha256(
                str(worktree.resolve()).encode()
            ).hexdigest()[:12]
            unit_directory = root / "units"
            unit_directory.mkdir()
            registered_unit = unit_directory / (
                f"polyscope-api-worktree-mighty-hyena-{runtime_id}-scheduler.service"
            )
            removed_unit = unit_directory / (
                "polyscope-api-worktree-removed-workspace-bbbbbbbbbbbb-scheduler.service"
            )
            registered_unit.write_text("registered\n")
            removed_unit.write_text("removed\n")
            systemctl = mock.Mock()
            reconcile_runtime_units = rollout.reconcile_api_runtime_units

            def reconcile(desired_units, **kwargs):
                reconcile_runtime_units(
                    desired_units,
                    unit_directory=unit_directory,
                    systemctl_runner=systemctl,
                    **kwargs,
                )

            with mock.patch.multiple(
                rollout,
                should_manage_api_runtime_units=mock.Mock(return_value=True),
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
                    side_effect=contextlib.nullcontext
                ),
                collect_linked_setup_context=mock.Mock(return_value={}),
                resolve_current_workspace_name=mock.Mock(
                    return_value="mighty-hyena"
                ),
                build_setup_hash=mock.Mock(return_value="setup-hash"),
                ensure_api_worktree_ready=mock.Mock(
                    return_value=(True, "database:preview")
                ),
                load_provision_marker=mock.Mock(
                    return_value={
                        "setup_hash": "setup-hash",
                        "preview_storage_target": "database:preview",
                    }
                ),
                build_api_runtime_revision=mock.Mock(
                    side_effect=RuntimeError("transient fingerprint failure")
                ),
                reconcile_api_runtime_units=mock.Mock(side_effect=reconcile),
            ):
                _provisioned, _cleaned, failures = rollout.provision_worktrees(
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

            self.assertEqual(len(failures), 1)
            self.assertTrue(registered_unit.exists())
            self.assertFalse(removed_unit.exists())
            commands = [call.args[0] for call in systemctl.call_args_list]
            self.assertNotIn(
                ["systemctl", "--user", "disable", "--now", registered_unit.name],
                commands,
            )
            self.assertIn(
                ["systemctl", "--user", "disable", "--now", removed_unit.name],
                commands,
            )

    def test_acl_reconciliation_continues_revoking_after_one_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            clone_root = Path(temporary_directory) / "clones"
            repo_root = clone_root / "frontend-id"
            first_orphan = repo_root / "aaa-orphan"
            later_orphan = repo_root / "zzz-orphan"
            first_orphan.mkdir(parents=True)
            later_orphan.mkdir()
            denied: list[Path] = []

            def deny(_clone_root, worktree_path, **_kwargs):
                denied.append(worktree_path)
                if worktree_path == first_orphan:
                    raise RuntimeError("simulated ACL denial failure")

            with (
                mock.patch.object(rollout, "deny_preview_nginx_access", new=deny),
                self.assertRaisesRegex(RuntimeError, first_orphan.name),
            ):
                rollout.revoke_unregistered_preview_nginx_access(
                    clone_root,
                    {"frontend": []},
                )

            self.assertEqual(denied, [first_orphan, later_orphan])

    def test_acl_reconciliation_revokes_worktrees_despite_bad_alias_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            clone_root = Path(temporary_directory) / "clones"
            first_repo = clone_root / "aaa-repo"
            later_repo = clone_root / "zzz-repo"
            first_orphan = first_repo / "orphan"
            later_orphan = later_repo / "orphan"
            first_orphan.mkdir(parents=True)
            later_orphan.mkdir(parents=True)
            (first_repo / rollout.WORKSPACE_ALIAS_REGISTRY_FILENAME).write_text("{bad-json\n")
            denied: list[Path] = []

            with (
                mock.patch.object(
                    rollout,
                    "deny_preview_nginx_access",
                    side_effect=lambda _root, worktree, **_kwargs: denied.append(worktree),
                ),
                self.assertRaisesRegex(RuntimeError, "workspace alias registry"),
            ):
                rollout.revoke_unregistered_preview_nginx_access(
                    clone_root,
                    {"frontend": []},
                )

            self.assertEqual(denied, [first_orphan, later_orphan])

    def test_acl_reconciliation_continues_after_repository_listing_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            clone_root = Path(temporary_directory) / "clones"
            first_repo = clone_root / "aaa-repo"
            later_repo = clone_root / "zzz-repo"
            first_repo.mkdir(parents=True)
            later_orphan = later_repo / "orphan"
            later_orphan.mkdir(parents=True)
            denied: list[Path] = []
            original_iterdir = Path.iterdir

            def iterdir(path):
                if path == first_repo:
                    raise OSError("simulated repository listing failure")
                return original_iterdir(path)

            with (
                mock.patch.object(Path, "iterdir", new=iterdir),
                mock.patch.object(
                    rollout,
                    "deny_preview_nginx_access",
                    side_effect=lambda _root, worktree, **_kwargs: denied.append(worktree),
                ),
                self.assertRaisesRegex(RuntimeError, first_repo.name),
            ):
                rollout.revoke_unregistered_preview_nginx_access(
                    clone_root,
                    {"frontend": []},
                )

            self.assertEqual(denied, [later_orphan])

    def test_scheduler_readiness_waits_for_a_real_heartbeat(self) -> None:
        runner = mock.Mock(
            side_effect=[
                SimpleNamespace(returncode=1),
                SimpleNamespace(returncode=0),
            ]
        )
        sleeper = mock.Mock()

        rollout.wait_for_api_scheduler_readiness(
            Path("/preview/api"),
            Path("/source/api"),
            command_runner=runner,
            sleeper=sleeper,
            attempts=2,
            interval_seconds=0.01,
        )

        self.assertEqual(runner.call_count, 2)
        sleeper.assert_called_once_with(0.01)
        command = runner.call_args_list[0].args[0]
        self.assertEqual(command[:3], ["php", "artisan", "tinker"])
        self.assertEqual(len(command), 4)
        self.assertTrue(command[3].startswith("--execute="), command)
        self.assertIn("schedulerReadiness", " ".join(command[2:]))
        self.assertIn("RuntimeException", " ".join(command[2:]))
        self.assertNotIn("exit(", " ".join(command[2:]))

    def test_scheduler_readiness_avoids_implicit_string_concatenation(self) -> None:
        source = inspect.getsource(rollout.wait_for_api_scheduler_readiness)
        ignored_tokens = {
            tokenize.COMMENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
            tokenize.INDENT,
            tokenize.NEWLINE,
            tokenize.NL,
        }
        significant_tokens = [
            token
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type not in ignored_tokens
        ]

        adjacent_string_tokens = [
            (left, right)
            for left, right in zip(significant_tokens, significant_tokens[1:])
            if left.type == tokenize.STRING and right.type == tokenize.STRING
        ]

        self.assertEqual(adjacent_string_tokens, [])

    def test_provision_mode_always_refreshes_nginx_without_a_unit_flag(self) -> None:
        args = SimpleNamespace(provision_worktrees=True, refresh_nginx=False)

        rollout.apply_canonical_reconcile_mode(args)

        self.assertTrue(args.refresh_nginx)

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
                    side_effect=contextlib.nullcontext
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
