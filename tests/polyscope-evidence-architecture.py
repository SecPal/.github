#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Polyscope rollout evidence for canonical runtime-baseline enforcement."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
import unittest.mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "polyscope_rollout_evidence", ROOT / "scripts" / "polyscope-rollout.py"
)
rollout = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(rollout)


class PolyscopeEvidenceArchitectureTests(unittest.TestCase):
    def test_runtime_baseline_supported_delegation_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("AGENTS.md").write_text(
                "# Runtime\n\n`docs/work-graph-contract.md` is canonical.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                rollout.validate_evidence_architecture_root(root, ".github"), root.resolve()
            )

    def test_missing_runtime_baseline_delegation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("AGENTS.md").write_text("# Runtime\n", encoding="utf-8")
            with self.assertRaisesRegex(
                rollout.CanonicalInstructionValidationError,
                "MISSING_RUNTIME_BASELINE_DELEGATION",
            ):
                rollout.validate_evidence_architecture_root(root, "api")

    def test_registration_only_managed_repository_is_still_validated(self):
        root = Path("/managed/operations")
        specs = {
            "operations": {
                "path": root,
                "repository_name": "operations",
                rollout.REGISTRATION_ONLY_SPEC_KEY: True,
            }
        }
        with unittest.mock.patch.object(
            rollout, "validate_evidence_architecture_root", return_value=root
        ) as evidence_validator, unittest.mock.patch.object(
            rollout, "validate_instruction_root"
        ) as instruction_validator, unittest.mock.patch.object(
            rollout, "validate_managed_evidence_architecture"
        ) as managed_validator:
            rollout.validate_repo_instruction_files(specs, set())

        evidence_validator.assert_called_once_with(root, "operations")
        instruction_validator.assert_not_called()
        managed_validator.assert_called_once()

    def test_managed_declarations_are_validated_as_one_bundle(self):
        specs = {
            "one": {"path": Path("/managed/one"), "repository_name": "one"},
            "two": {"path": Path("/managed/two"), "repository_name": "two"},
        }
        with unittest.mock.patch.object(rollout.subprocess, "run") as run:
            run.return_value = unittest.mock.Mock(
                returncode=0, stdout="{}", stderr=""
            )
            rollout.validate_managed_evidence_architecture(
                Path("/managed"), specs
            )

        command = run.call_args.args[0]
        self.assertIn("--managed-workspace-root", command)
        self.assertEqual(command.count("--managed-repository"), 2)
        self.assertEqual(command[-4:], ["--managed-repository", "one", "--managed-repository", "two"])

    def test_provisionability_validates_active_worktree_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath(".git").mkdir()
            with unittest.mock.patch.object(
                rollout, "resolve_git_dir", return_value=root / ".git"
            ), unittest.mock.patch.object(
                rollout, "validate_instruction_root", return_value=root
            ), unittest.mock.patch.object(
                rollout, "validate_evidence_architecture_root", return_value=root
            ) as evidence, unittest.mock.patch.object(
                rollout, "load_package_scripts", return_value={}
            ), unittest.mock.patch.object(
                rollout, "load_composer_scripts", return_value={}
            ):
                self.assertTrue(
                    rollout.is_provisionable_worktree(
                        "api", root, [], validated_instruction_roots=set()
                    )
                )

        evidence.assert_called_once_with(root, "api")

    def test_direct_api_modes_validate_source_and_active_worktree_evidence(self):
        source = Path("/managed/api")
        worktree = Path("/managed/worktree")
        with unittest.mock.patch.object(
            rollout, "validate_instruction_root", side_effect=[source, worktree]
        ), unittest.mock.patch.object(
            rollout, "validate_evidence_architecture_root"
        ) as evidence:
            self.assertEqual(
                rollout.validate_direct_api_worktree_roots(source, worktree),
                (source, worktree),
            )

        self.assertEqual(
            evidence.call_args_list,
            [unittest.mock.call(source, "api"), unittest.mock.call(worktree, "api")],
        )


if __name__ == "__main__":
    unittest.main()
