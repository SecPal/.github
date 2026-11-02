#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import importlib.util
import pathlib
import subprocess
import tempfile
from unittest import TestCase, main, mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("api_tests", ROOT / "scripts/run-polyscope-api-tests.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class IsolatedApiTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = pathlib.Path(self.temporary.name)
        for name in ("artisan", "phpunit.xml", "composer.lock"):
            (self.workspace / name).touch()
        self.commands = []
        self.environments = []
        self.sql = []
        self.status = 0
        self.ready = True
        self.fail_initialization = False
        self.interrupt = False
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.chdir(self.workspace))
        stack.enter_context(mock.patch.object(runner.os, "geteuid", return_value=1000))
        stack.enter_context(mock.patch.object(runner.subprocess, "check_output", return_value="/canonical/api/.git\n"))
        stack.enter_context(mock.patch.object(runner, "podman", side_effect=self.podman))
        stack.enter_context(mock.patch.object(runner.subprocess, "run", side_effect=self.process))

    def podman(self, arguments, **kwargs):
        self.commands.append(arguments)
        if arguments[:1] == ["info"]:
            return subprocess.CompletedProcess(arguments, 0, "true\n")
        if arguments[:2] == ["network", "create"]:
            return subprocess.CompletedProcess(arguments, 0, "isolated-network\n")
        if arguments[:1] == ["create"]:
            env_file = pathlib.Path(arguments[arguments.index("--env-file") + 1])
            self.environments.append((env_file, env_file.read_text(), env_file.stat().st_mode & 0o777))
            return subprocess.CompletedProcess(arguments, 0, "database\n" if arguments[-1] == runner.POSTGRES_IMAGE else "application\n")
        if arguments[:1] == ["exec"] and "psql" in arguments:
            self.sql.append(kwargs["input"])
            if self.fail_initialization:
                raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0)

    def process(self, command, **_kwargs):
        self.commands.append(command[1:])
        if "pg_isready" in command:
            return subprocess.CompletedProcess(command, 0 if self.ready else 1)
        if command[1:4] == ["start", "--attach", "--interactive"]:
            if self.interrupt:
                raise SystemExit(143)
            return subprocess.CompletedProcess(command, self.status)
        return subprocess.CompletedProcess(command, 0)

    def execute(self, *arguments):
        return runner.run_tests("localhost/test-image:qualified", list(arguments))

    def assert_cleaned(self, application=True):
        expected = ([["rm", "--force", "--volumes", "application"]] if application else []) + [
            ["rm", "--force", "--volumes", "database"], ["network", "rm", "isolated-network"]]
        self.assertEqual(self.commands[-len(expected):], expected)
        self.assertTrue(all(not path.exists() for path, _, _ in self.environments))

    def test_success_is_private_and_uses_a_non_superuser_test_identity(self):
        self.assertEqual(self.execute("--parallel", "--processes=2"), 0)
        network = next(c for c in self.commands if c[:2] == ["network", "create"])
        self.assertIn("--internal", network)
        application = [c for c in self.commands if c[:1] == ["create"]][-1]
        self.assertIn("--userns=keep-id:uid=1000,gid=1000", application)
        self.assertIn("--no-healthcheck", application)
        self.assertTrue(all("-p" not in c and "--publish" not in c and "polyscope-postgresql-proxy" not in c for c in self.commands))
        self.assertTrue(all(mode == 0o600 for _, _, mode in self.environments))
        app_env = self.environments[1][1]
        self.assertIn("DB_HOST=database\n", app_env)
        self.assertIn("DB_USERNAME=testing\n", app_env)
        self.assertIn("DB_URL=\n", app_env)
        self.assertIn("CREATEDB NOSUPERUSER NOCREATEROLE NOREPLICATION", self.sql[0])
        self.assertNotIn("SUPERUSER PASSWORD", self.sql[0])
        self.assert_cleaned()

    def test_test_failure_is_returned_and_all_resources_are_cleaned(self):
        self.status = 7
        self.assertEqual(self.execute("tests/Feature"), 7)
        self.assert_cleaned()

    def test_full_mode_uses_the_existing_composer_test_script(self):
        self.assertEqual(self.execute("--full"), 0)
        application = [c for c in self.commands if c[:1] == ["create"]][-1]
        self.assertEqual(application[-2:], ["composer", "test"])
        self.assert_cleaned()

    def test_initialization_failure_never_launches_application_tests(self):
        self.fail_initialization = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute()
        self.assertNotIn(["start", "--attach", "--interactive", "application"], self.commands)
        self.assert_cleaned(application=False)

    def test_unreachable_database_fails_closed_and_cleans_up(self):
        self.ready = False
        with mock.patch.object(runner.time, "monotonic", side_effect=[0, 100]):
            with self.assertRaisesRegex(RuntimeError, "no preview fallback"):
                self.execute()
        self.assert_cleaned(application=False)

    def test_interruption_cleans_application_database_network_and_credentials(self):
        self.interrupt = True
        with self.assertRaises(SystemExit):
            self.execute()
        self.assert_cleaned()


if __name__ == "__main__":
    main()
