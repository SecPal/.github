# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "secpal-trivy-repository-scan.py"
POLICY = ROOT / "policies" / "trivy-repository-scan-v1.json"
SCHEMA = ROOT / "docs" / "schemas" / "secpal-trivy-repository-scan-v1.schema.json"
ACTION = ROOT / ".github" / "actions" / "trivy-repository-scan" / "action.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "trivy-repository-scan"
COMMIT = "1" * 40
SYNTHETIC_SECRET = "SECPAL_SYNTHETIC_SECRET_" + "A1B2C3D4E5F6G7H8"


def load_module():
    spec = importlib.util.spec_from_file_location("repository_scan", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load repository scan module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_result() -> dict:
    return {
        "SchemaVersion": 2,
        "ArtifactName": ".",
        "ArtifactType": "filesystem",
        "Results": [
            {
                "Target": "package-lock.json",
                "Class": "lang-pkgs",
                "Type": "npm",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2021-23337",
                        "PkgName": "lodash",
                        "InstalledVersion": "4.17.20",
                        "FixedVersion": "4.17.21",
                        "Severity": "HIGH",
                        "Title": "Command injection",
                    }
                ],
            },
            {
                "Target": "config/synthetic.env",
                "Class": "secret",
                "Secrets": [
                    {
                        "RuleID": "secpal-synthetic-secret",
                        "Category": "General",
                        "Severity": "HIGH",
                        "Title": "SecPal synthetic test secret",
                        "StartLine": 3,
                        "EndLine": 3,
                        "Match": SYNTHETIC_SECRET,
                        "Code": f'SYNTHETIC_TOKEN="{SYNTHETIC_SECRET}"',
                    }
                ],
            },
            {
                "Target": "Containerfile",
                "Class": "config",
                "Type": "dockerfile",
                "Misconfigurations": [
                    {
                        "Type": "Dockerfile Security Check",
                        "ID": "DS002",
                        "AVDID": "AVD-DS-0002",
                        "Title": "Image runs as root",
                        "Message": "Specify a non-root USER command",
                        "Severity": "HIGH",
                        "Status": "FAIL",
                        "CauseMetadata": {
                            "StartLine": 1,
                            "EndLine": 1,
                            "Resource": "alpine:3.20",
                        },
                    }
                ],
            },
        ],
    }


class RepositoryScanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))

    def test_action_has_closed_interface_and_pinned_scanner(self) -> None:
        source = ACTION.read_text(encoding="utf-8")
        self.assertIn("TRIVY_VERSION: 0.74.0", source)
        self.assertIn(
            "TRIVY_ARCHIVE_SHA256: 2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a",
            source,
        )
        self.assertIn("--scanners vuln,secret,misconfig", source)
        self.assertIn("--skip-check-update", source)
        self.assertNotIn("repository:", source)
        self.assertNotIn("ref:", source)
        self.assertNotIn("github-token", source)
        self.assertIn("retention-days: 14", source)
        self.assertIn("env -i", source)
        self.assertIn('--config "$trusted_config"', source)
        self.assertIn("git -C \"$GITHUB_WORKSPACE\" ls-files -v", source)
        self.assertIn("secrets.token_hex", source)

    def test_normalization_redacts_secret_and_preserves_all_scanner_context(self) -> None:
        observation = self.module.normalize_native(
            native_result(),
            repository="SecPal/example",
            commit=COMMIT,
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
            },
            database={
                "status": "FRESH",
                "identity": "sha256:" + "b" * 64,
                "updated_at": "2026-09-16T10:00:00Z",
                "next_update": "2026-09-17T10:00:00Z",
                "downloaded_at": "2026-09-16T10:05:00Z",
            },
            completed_at="2026-09-16T10:10:00Z",
        )
        encoded = json.dumps(observation, sort_keys=True)
        self.assertNotIn(SYNTHETIC_SECRET, encoded)
        self.assertNotIn("Match", encoded)
        self.assertNotIn("Code", encoded)
        self.assertEqual(
            {finding["class"] for finding in observation["findings"]},
            {"VULNERABILITY", "SECRET", "MISCONFIGURATION"},
        )
        secret = next(item for item in observation["findings"] if item["class"] == "SECRET")
        self.assertEqual(secret["rule_id"], "secpal-synthetic-secret")
        self.assertEqual(secret["path"], "config/synthetic.env")
        self.assertEqual(secret["location"], {"start_line": 3, "end_line": 3})
        misconfiguration = next(
            item for item in observation["findings"] if item["class"] == "MISCONFIGURATION"
        )
        self.assertEqual(misconfiguration["rule_id"], "AVD-DS-0002")
        self.assertEqual(misconfiguration["resource"], "alpine:3.20")

    def test_admission_is_deterministic_and_policy_owned(self) -> None:
        observation = self.module.normalize_native(
            native_result(),
            repository="SecPal/example",
            commit=COMMIT,
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
            },
            database={
                "status": "FRESH",
                "identity": "sha256:" + "b" * 64,
                "updated_at": "2026-09-16T10:00:00Z",
                "next_update": "2026-09-17T10:00:00Z",
                "downloaded_at": "2026-09-16T10:05:00Z",
            },
            completed_at="2026-09-16T10:10:00Z",
        )
        first = self.module.admit(observation, self.policy)
        second = self.module.admit(observation, self.policy)
        self.assertEqual(first, second)
        self.assertEqual(first["gate_state"], "ACTIONABLE")
        self.assertEqual(first["policy"]["id"], "secpal-trivy-repository-policy-v1")
        self.assertEqual(len({finding["fingerprint"] for finding in first["findings"]}), 3)

    def test_reviewed_exception_is_exact_bounded_and_expiring(self) -> None:
        native = native_result()
        native["Results"] = native["Results"][:1]
        observation = self.module.normalize_native(
            native,
            repository="SecPal/example",
            commit=COMMIT,
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
            },
            database={
                "status": "FRESH",
                "identity": "sha256:" + "b" * 64,
                "updated_at": "2026-09-16T10:00:00Z",
                "next_update": "2026-09-17T10:00:00Z",
                "downloaded_at": "2026-09-16T10:05:00Z",
            },
            completed_at="2026-09-16T10:10:00Z",
        )
        policy = copy.deepcopy(self.policy)
        policy["exceptions"] = [
            {
                "id": "SEC-EXAMPLE-1",
                "class": "VULNERABILITY",
                "rule_id": "CVE-2021-23337",
                "path": "package-lock.json",
                "disposition": "NOT_AFFECTED",
                "expires_at": "2026-10-01T00:00:00Z",
                "rationale": "Synthetic bounded policy fixture.",
            }
        ]
        result = self.module.admit(observation, policy)
        self.assertEqual(result["gate_state"], "CLEAN")
        self.assertEqual(result["summary"]["excepted"], 1)
        self.assertEqual(result["findings"][0]["exception"]["id"], "SEC-EXAMPLE-1")

        policy["exceptions"][0]["expires_at"] = "2026-09-16T10:10:00Z"
        with self.assertRaises(self.module.ContractError):
            self.module.admit(observation, policy)

    def test_exception_paths_are_canonical_and_selectors_are_unique(self) -> None:
        native = native_result()
        native["Results"] = native["Results"][:1]
        observation = self.module.normalize_native(
            native,
            repository="SecPal/example",
            commit=COMMIT,
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
            },
            database={
                "status": "FRESH",
                "identity": "sha256:" + "b" * 64,
                "updated_at": "2026-09-16T10:00:00Z",
                "next_update": "2026-09-17T10:00:00Z",
                "downloaded_at": "2026-09-16T10:05:00Z",
            },
            completed_at="2026-09-16T10:10:00Z",
        )
        policy = copy.deepcopy(self.policy)
        exception = {
            "id": "SEC-EXAMPLE-1",
            "class": "VULNERABILITY",
            "rule_id": "CVE-2021-23337",
            "path": "./package-lock.json",
            "disposition": "NOT_AFFECTED",
            "expires_at": "2026-10-01T00:00:00Z",
            "rationale": "Synthetic bounded policy fixture.",
        }
        policy["exceptions"] = [exception]
        result = self.module.admit(observation, policy)
        self.assertEqual(result["gate_state"], "CLEAN")

        duplicate = copy.deepcopy(exception)
        duplicate["id"] = "SEC-EXAMPLE-2"
        duplicate["path"] = "package-lock.json"
        policy["exceptions"].append(duplicate)
        with self.assertRaisesRegex(self.module.ContractError, "selectors must be unique"):
            self.module.admit(observation, policy)

    def test_secret_without_location_is_rejected(self) -> None:
        native = native_result()
        del native["Results"][1]["Secrets"][0]["StartLine"]
        del native["Results"][1]["Secrets"][0]["EndLine"]
        with self.assertRaisesRegex(self.module.ContractError, "secret location"):
            self.module.normalize_native(
                native,
                repository="SecPal/example",
                commit=COMMIT,
                scanner={
                    "name": "trivy",
                    "version": "0.74.0",
                    "immutable_id": "sha256:" + "a" * 64,
                },
                database={
                    "status": "FRESH",
                    "identity": "sha256:" + "b" * 64,
                    "updated_at": "2026-09-16T10:00:00Z",
                    "next_update": "2026-09-17T10:00:00Z",
                    "downloaded_at": "2026-09-16T10:05:00Z",
                },
                completed_at="2026-09-16T10:10:00Z",
            )

    def test_malformed_and_stale_evidence_never_becomes_clean(self) -> None:
        with self.assertRaises(self.module.ContractError):
            self.module.normalize_native(
                {"SchemaVersion": 2, "Results": "invalid"},
                repository="SecPal/example",
                commit=COMMIT,
                scanner={"name": "trivy", "version": "0.74.0", "immutable_id": "sha256:" + "a" * 64},
                database={"status": "FRESH"},
                completed_at="2026-09-16T10:10:00Z",
            )
        unknown = self.module.unknown_result(
            repository="SecPal/example",
            commit=COMMIT,
            failure_code="MALFORMED_OUTPUT",
            completed_at="2026-09-16T10:10:00Z",
        )
        self.assertEqual(unknown["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(unknown["operation"]["status"], "FAILED")
        network = self.module.unknown_result(
            repository="SecPal/example",
            commit=COMMIT,
            failure_code="NETWORK_FAILURE",
            completed_at="2026-09-16T10:10:00Z",
        )
        self.assertEqual(network["gate_state"], "UNKNOWN_STALE")

        clean_native = native_result()
        clean_native["Results"] = []
        observation = self.module.normalize_native(
            clean_native,
            repository="SecPal/example",
            commit=COMMIT,
            scanner={"name": "trivy", "version": "0.74.0", "immutable_id": "sha256:" + "a" * 64},
            database=json.loads((FIXTURES / "stale-database.json").read_text(encoding="utf-8")),
            completed_at="2026-09-16T10:10:00Z",
        )
        stale = self.module.admit(observation, self.policy)
        self.assertEqual(stale["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(stale["operation"], {
            "name": "TRIVY_REPOSITORY_SCAN",
            "status": "FAILED",
            "failure_code": "DATABASE_FAILURE",
        })
        import jsonschema

        jsonschema.validate(stale, json.loads(SCHEMA.read_text(encoding="utf-8")))

    def test_schema_accepts_result_and_rejects_secret_capture_fields(self) -> None:
        import jsonschema

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        unknown = self.module.unknown_result(
            repository="SecPal/example",
            commit=COMMIT,
            failure_code="NETWORK_FAILURE",
            completed_at="2026-09-16T10:10:00Z",
        )
        jsonschema.validate(unknown, schema)
        finding_schema = schema["$defs"]["finding"]
        self.assertFalse(finding_schema.get("additionalProperties", True))
        self.assertNotIn("match", finding_schema["properties"])
        self.assertNotIn("code", finding_schema["properties"])

        observation = self.module.normalize_native(
            native_result(),
            repository="SecPal/example",
            commit=COMMIT,
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
            },
            database={
                "status": "FRESH",
                "identity": "sha256:" + "b" * 64,
                "updated_at": "2026-09-16T10:00:00Z",
                "next_update": "2026-09-17T10:00:00Z",
                "downloaded_at": "2026-09-16T10:05:00Z",
            },
            completed_at="2026-09-16T10:10:00Z",
        )
        successful = self.module.admit(observation, self.policy)
        jsonschema.validate(successful, schema)
        unsafe = copy.deepcopy(successful)
        secret = next(item for item in unsafe["findings"] if item["class"] == "SECRET")
        secret["message"] = SYNTHETIC_SECRET
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(unsafe, schema)

    def test_cli_returns_nonzero_unknown_for_malformed_native_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            native = root / "native.json"
            output = root / "result.json"
            native.write_bytes((FIXTURES / "malformed.txt").read_bytes())
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "evaluate",
                    "--native",
                    str(native),
                    "--policy",
                    str(POLICY),
                    "--repository",
                    "SecPal/example",
                    "--commit",
                    COMMIT,
                    "--scanner-version",
                    "0.74.0",
                    "--scanner-identity",
                    "sha256:" + "a" * 64,
                    "--database",
                    str(root / "missing-database.json"),
                    "--completed-at",
                    "2026-09-16T10:10:00Z",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
            self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")
            self.assertNotIn("{not-json", completed.stdout + completed.stderr)

    def test_cli_reports_invalid_policy_as_policy_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            native = root / "native.json"
            database = root / "database.json"
            policy = root / "policy.json"
            output = root / "result.json"
            native.write_text(json.dumps(native_result()), encoding="utf-8")
            database.write_text(
                json.dumps(
                    {
                        "status": "FRESH",
                        "identity": "sha256:" + "b" * 64,
                        "updated_at": "2026-09-16T10:00:00Z",
                        "next_update": "2026-09-17T10:00:00Z",
                        "downloaded_at": "2026-09-16T10:05:00Z",
                    }
                ),
                encoding="utf-8",
            )
            policy.write_text("{not-json", encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3", str(SCRIPT), "evaluate",
                    "--native", str(native), "--database", str(database),
                    "--policy", str(policy), "--repository", "SecPal/example",
                    "--commit", COMMIT, "--scanner-version", "0.74.0",
                    "--scanner-identity", "sha256:" + "a" * 64,
                    "--completed-at", "2026-09-16T10:10:00Z",
                    "--output", str(output),
                ],
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["operation"]["failure_code"], "POLICY_FAILURE")


if __name__ == "__main__":
    unittest.main()
