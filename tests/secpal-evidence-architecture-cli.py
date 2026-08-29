#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Integration evidence for the #736 closed declaration CLI."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "secpal-evidence-architecture.py"


class EvidenceArchitectureCliTests(unittest.TestCase):
    def run_cli(self, repository_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(CLI),
                "--repository-root",
                str(repository_root),
                "--repository",
                "SecPal/example",
                *arguments,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def fixture(self, agents: str) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
        return temporary, root

    def test_top_level_supported_work_graph_reference_passes(self):
        temporary, root = self.fixture(
            "# Runtime\n\nUse [`work graph`](https://github.com/SecPal/.github/blob/main/docs/work-graph-contract.md).\n"
        )
        with temporary:
            result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["runtime_baseline"]["state"],
            "VALID_TRANSITIVE_SUPPORTED_DELEGATION",
        )

    def test_fenced_quoted_and_commented_examples_do_not_delegate(self):
        temporary, root = self.fixture(
            """# Runtime

> `docs/evidence-architecture-contract.md`

```text
docs/work-graph-contract.md
```

<!-- `docs/evidence-architecture-contract.md` -->
"""
        )
        with temporary:
            result = self.run_cli(root)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stdout)["runtime_baseline"]["state"], "MISSING_DELEGATION"
        )

    def test_closed_declaration_and_executable_proof_are_consumed(self):
        temporary, root = self.fixture(
            "# Runtime\n\n`docs/evidence-architecture-contract.md` is canonical.\n"
        )
        with temporary:
            declaration_dir = root / ".secpal"
            declaration_dir.mkdir()
            declaration_dir.joinpath("evidence-architecture.json").write_text(
                json.dumps(
                    {
                        "schema": "secpal-evidence-architecture/v1",
                        "repository": "SecPal/example",
                        "runtime_baseline": {
                            "delegation": "direct",
                            "generic_authorities": [
                                "docs/evidence-architecture-contract.md"
                            ],
                        },
                        "external_operations": [
                            {
                                "id": "provider.observe",
                                "reachable": True,
                                "fallible": True,
                                "trusted": True,
                                "diagnostic_identity": {
                                    "id": "provider.observe.failed",
                                    "kind": "semantic",
                                },
                            }
                        ],
                        "pure_surfaces": [],
                        "invariant_declarations": [],
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cli(root, "--dispatch")
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertTrue(document["dispatch_requested"])
        self.assertEqual(document["external_operation_count"], 1)

    def test_dispatch_without_declared_operations_fails(self):
        temporary, root = self.fixture(
            "# Runtime\n\n`docs/evidence-architecture-contract.md` is canonical.\n"
        )
        with temporary:
            declaration_dir = root / ".secpal"
            declaration_dir.mkdir()
            declaration_dir.joinpath("evidence-architecture.json").write_text(
                json.dumps(
                    {
                        "schema": "secpal-evidence-architecture/v1",
                        "repository": "SecPal/example",
                        "runtime_baseline": {
                            "delegation": "direct",
                            "generic_authorities": [
                                "docs/evidence-architecture-contract.md"
                            ],
                        },
                        "external_operations": [],
                        "pure_surfaces": [],
                        "invariant_declarations": [],
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cli(root, "--dispatch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DISPATCH_DECLARATION_MISSING", result.stdout)

    def test_oversized_declaration_retains_no_attacker_body(self):
        temporary, root = self.fixture(
            "# Runtime\n\n`docs/evidence-architecture-contract.md` is canonical.\n"
        )
        with temporary:
            declaration_dir = root / ".secpal"
            declaration_dir.mkdir()
            declaration_dir.joinpath("evidence-architecture.json").write_text(
                "secret-provider-body:" + "x" * 70000,
                encoding="utf-8",
            )
            result = self.run_cli(root, "--dispatch")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("secret-provider-body", result.stdout + result.stderr)
        self.assertIn("DECLARATION_EVIDENCE_UNAVAILABLE", result.stdout)

    def test_symlinked_declaration_is_not_accepted_as_repository_authority(self):
        temporary, root = self.fixture(
            "# Runtime\n\n`docs/evidence-architecture-contract.md` is canonical.\n"
        )
        with temporary:
            actual = root / "actual-declaration.json"
            actual.write_text(
                json.dumps(
                    {
                        "schema": "secpal-evidence-architecture/v1",
                        "repository": "SecPal/example",
                        "runtime_baseline": {
                            "delegation": "direct",
                            "generic_authorities": [
                                "docs/evidence-architecture-contract.md"
                            ],
                        },
                        "external_operations": [
                            {
                                "id": "provider.observe",
                                "reachable": True,
                                "fallible": True,
                                "trusted": True,
                                "diagnostic_identity": {
                                    "id": "provider.observe.failed",
                                    "kind": "semantic",
                                },
                            }
                        ],
                        "pure_surfaces": [],
                        "invariant_declarations": [],
                    }
                ),
                encoding="utf-8",
            )
            declaration_dir = root / ".secpal"
            declaration_dir.mkdir()
            declaration_dir.joinpath("evidence-architecture.json").symlink_to(actual)
            result = self.run_cli(root, "--dispatch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DECLARATION_EVIDENCE_UNAVAILABLE", result.stdout)

    def test_managed_bundle_rejects_duplicate_owners_across_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for name in ("one", "two"):
                root = workspace / name
                declaration_dir = root / ".secpal"
                declaration_dir.mkdir(parents=True)
                root.joinpath("AGENTS.md").write_text(
                    "# Runtime\n\n`docs/work-graph-contract.md` is canonical.\n",
                    encoding="utf-8",
                )
                declaration_dir.joinpath("evidence-architecture.json").write_text(
                    json.dumps(
                        {
                            "schema": "secpal-evidence-architecture/v1",
                            "repository": f"SecPal/{name}",
                            "runtime_baseline": {
                                "delegation": "transitive_work_graph",
                                "generic_authorities": [
                                    "docs/work-graph-contract.md"
                                ],
                            },
                            "external_operations": [],
                            "pure_surfaces": [],
                            "invariant_declarations": [
                                {
                                    "id": f"{name}.owner",
                                    "invariant": "shared.invariant",
                                    "role": "owner",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
            result = subprocess.run(
                [
                    "python3",
                    str(CLI),
                    "--managed-workspace-root",
                    str(workspace),
                    "--managed-repository",
                    "one",
                    "--managed-repository",
                    "two",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("DUPLICATE_INVARIANT_OWNER", result.stdout)


if __name__ == "__main__":
    unittest.main()
