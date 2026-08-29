#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT

"""Integration evidence for the #736 closed declaration CLI."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "secpal-evidence-architecture.py"
sys.path.insert(0, str(ROOT / "scripts"))
from secpal_pr_review import fast_path, lifecycle_authority  # noqa: E402
SPEC = importlib.util.spec_from_file_location("evidence_cli", CLI)
evidence_cli = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(evidence_cli)


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

    def proof_fixture(self, status: str = "passed") -> tuple[tempfile.TemporaryDirectory, Path, dict]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", root], check=True)
        subprocess.run(["git", "-C", root, "config", "user.name", "Fixture"], check=True)
        subprocess.run(["git", "-C", root, "config", "user.email", "fixture@example.invalid"], check=True)
        root.joinpath("subject.txt").write_text("reviewed input\n", encoding="utf-8")
        subprocess.run(["git", "-C", root, "add", "subject.txt"], check=True)
        subprocess.run(["git", "-C", root, "commit", "-q", "-m", "fixture"], check=True)
        revision, tree = evidence_cli._git_identity(root)
        receipt_fields = {
            "schema_version": "1.0",
            "kind": "VALIDATION_RECEIPT",
            "repository": "SecPal/example",
            "head_sha": revision,
            "validated_tree_sha": tree,
            "registry_digest": "1" * 64,
            "command_set_digest": "2" * 64,
            "successful_result": True,
            "reviewed_state_digest": "3" * 64,
            "reviewed_feedback_digest": "4" * 64,
            "manual_gate_evidence": [],
            "eligibility_evidence_digest": "5" * 64,
        }
        payload = {
            "schema": evidence_cli.governance.PROOF_SCHEMA,
            "repository": "SecPal/example",
            "revision": revision,
            "tree": tree,
            "producer": "trusted-authority",
            "validation_receipt": {
                **receipt_fields,
                "receipt_digest": fast_path.digest_json(receipt_fields),
            },
            "results": [{
                "id": "host-digest-agreement",
                "kind": "executable",
                "status": status,
                "reviewed_input_id": "host-digest-real-world-cases",
                "reviewed_input_digest": "6" * 64,
            }],
        }
        return temporary, root, {"payload": payload, "signature": {"value": "fixture"}}

    def test_fabricated_static_pass_is_not_authenticated(self):
        temporary, root, _document = self.proof_fixture()
        with temporary, self.assertRaisesRegex(
            evidence_cli.EvidenceUnavailable, "authenticated envelope"
        ):
            evidence_cli._verified_agreement_results(
                root,
                "SecPal/example",
                {"schema": "secpal-evidence-agreement-results/v1", "results": [
                    {"id": "fabricated", "kind": "executable", "status": "passed"}
                ]},
            )

    def test_self_asserted_provenance_fields_do_not_create_authority(self):
        temporary, root, _document = self.proof_fixture()
        with temporary, self.assertRaisesRegex(
            evidence_cli.EvidenceUnavailable, "authenticated envelope"
        ):
            evidence_cli._verified_agreement_results(
                root,
                "SecPal/example",
                {"id": "fabricated", "status": "passed", "producer": "trusted-authority",
                 "revision": "a" * 40, "command": "tests pass", "timestamp": "now"},
            )

    def test_wrong_producer_is_rejected_by_maintained_signature_authority(self):
        temporary, root, document = self.proof_fixture()
        document["payload"]["producer"] = "wrong-producer"
        with temporary, mock.patch.object(
            lifecycle_authority,
            "verify_authority_signed_payload",
            side_effect=lifecycle_authority.LifecycleAuthorityError("untrusted"),
        ), self.assertRaisesRegex(evidence_cli.EvidenceUnavailable, "signature is invalid"):
            evidence_cli._verified_agreement_results(root, "SecPal/example", document)

    def test_wrong_revision_is_rejected_before_signature_verification(self):
        temporary, root, document = self.proof_fixture()
        document["payload"]["revision"] = "a" * 40
        with temporary, mock.patch.object(
            lifecycle_authority, "verify_authority_signed_payload"
        ) as verifier, self.assertRaisesRegex(
            evidence_cli.EvidenceUnavailable, "producer or subject is stale"
        ):
            evidence_cli._verified_agreement_results(root, "SecPal/example", document)
        verifier.assert_not_called()

    def test_authenticated_matching_execution_proof_passes(self):
        temporary, root, document = self.proof_fixture()
        with temporary, mock.patch.object(
            lifecycle_authority,
            "verify_authority_signed_payload",
            return_value={"format": "ssh", "signer_identity": "trusted-authority", "value": "fixture"},
        ) as verifier:
            results = evidence_cli._verified_agreement_results(root, "SecPal/example", document)
        self.assertEqual(results, [evidence_cli.governance.VerifiedAgreementResult(
            "host-digest-agreement", "passed"
        )])
        verifier.assert_called_once()

    def test_authenticated_failed_or_unavailable_proof_does_not_pass_governance(self):
        for status in ("failed", "unavailable"):
            with self.subTest(status=status):
                temporary, root, document = self.proof_fixture(status)
                with temporary, mock.patch.object(
                    lifecycle_authority,
                    "verify_authority_signed_payload",
                    return_value={"format": "ssh", "signer_identity": "trusted-authority", "value": "fixture"},
                ):
                    results = evidence_cli._verified_agreement_results(root, "SecPal/example", document)
                declaration = {
                    "schema": "secpal-evidence-architecture/v1",
                    "repository": "SecPal/example",
                    "runtime_baseline": {"delegation": "direct", "generic_authorities": ["docs/evidence-architecture-contract.md"]},
                    "external_operations": [], "pure_surfaces": [],
                    "invariant_declarations": [
                        {"id": "owner", "invariant": "host.digest", "role": "owner"},
                        {"id": "edge", "invariant": "host.digest", "role": "independent_enforcement", "owner": "owner", "derivation": "same-cases", "agreement_proof": "host-digest-agreement"},
                    ],
                }
                report = evidence_cli.governance.assess_declarations([declaration], proof_results=results)
                self.assertEqual(report["status"], "blocked")

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
