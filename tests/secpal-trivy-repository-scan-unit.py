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


def valid_database() -> dict:
    return {
        "status": "FRESH",
        "identity": "sha256:" + "b" * 64,
        "updated_at": "2026-09-16T10:00:00Z",
        "next_update": "2026-09-17T10:00:00Z",
        "downloaded_at": "2026-09-16T10:05:00Z",
    }


def run_evaluate_fixture(
    native: dict,
    database: dict | None = None,
    completed_at: str = "2026-09-16T10:10:00Z",
) -> tuple[subprocess.CompletedProcess[bytes], dict]:
    import jsonschema

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        native_path = root / "native.json"
        database_path = root / "database.json"
        output = root / "result.json"
        native_path.write_text(json.dumps(native), encoding="utf-8")
        database_path.write_text(
            json.dumps(valid_database() if database is None else database),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "evaluate",
                "--native",
                str(native_path),
                "--database",
                str(database_path),
                "--policy",
                str(POLICY),
                "--repository",
                "SecPal/example",
                "--commit",
                COMMIT,
                "--workspace",
                ".",
                "--scanner-version",
                "0.74.0",
                "--scanner-identity",
                "sha256:" + "a" * 64,
                "--completed-at",
                completed_at,
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
        )
        result = json.loads(output.read_text(encoding="utf-8"))
        jsonschema.validate(result, json.loads(SCHEMA.read_text(encoding="utf-8")))
        return completed, result


def evaluate_fixture(native: dict, database: dict | None = None) -> dict:
    completed, result = run_evaluate_fixture(native, database)
    if completed.returncode == 0:
        raise AssertionError("malformed fixture unexpectedly succeeded")
    return result


def native_result() -> dict:
    return {
        "SchemaVersion": 2,
        "ArtifactName": ".",
        "ArtifactType": "repository",
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
        self.assertIn("--include-dev-deps", source)
        self.assertIn("--show-suppressed", source)
        self.assertNotIn("python3 -c", source)
        self.assertNotIn("python3 - ", source)
        self.assertIn("verify-redaction", source)
        self.assertIn('--output "$candidate"', source)
        self.assertLess(source.index("verify-redaction"), source.index('install -m 0600 "$candidate"'))
        self.assertIn('--output "$native" "$GITHUB_WORKSPACE" >/dev/null 2>"$tool_root/native.stderr"', source)
        self.assertNotIn("repository:", source)
        self.assertNotIn("ref:", source)
        self.assertNotIn("github-token", source)
        self.assertIn("retention-days: 14", source)
        self.assertIn("env -i", source)
        self.assertIn('--config "$trusted_config"', source)
        self.assertIn("verify-target", source)
        self.assertLess(source.index("verify-target"), source.index("curl --fail"))
        self.assertIn("secrets.token_hex", source)
        self.assertIn('--workspace "$GITHUB_WORKSPACE"', source)

    def _assert_index_flags_fail_target_identity(self, flags: list[str]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            tracked = workspace / "tracked.txt"
            tracked.write_text("original\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(workspace), "init", "--quiet"], check=True)
            subprocess.run(
                ["git", "-C", str(workspace), "config", "user.name", "SecPal Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(workspace), "config", "user.email", "test@secpal.app"],
                check=True,
            )
            subprocess.run(["git", "-C", str(workspace), "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(workspace), "commit", "--quiet", "-m", "fixture"],
                check=True,
            )
            commit = subprocess.run(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            clean = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "verify-target",
                    "--workspace",
                    str(workspace),
                    "--commit",
                    commit,
                ],
                check=False,
                capture_output=True,
            )
            self.assertEqual(clean.returncode, 0)

            for flag in flags:
                subprocess.run(
                    ["git", "-C", str(workspace), "update-index", flag, "tracked.txt"],
                    check=True,
                )
            tracked.write_text("modified but hidden\n", encoding="utf-8")
            status = subprocess.run(
                ["git", "-C", str(workspace), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(status, "")
            prefix = subprocess.run(
                ["git", "-C", str(workspace), "ls-files", "-v", "tracked.txt"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout[0]
            self.assertTrue(prefix.islower())

            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "verify-target",
                    "--workspace",
                    str(workspace),
                    "--commit",
                    commit,
                ],
                check=False,
                capture_output=True,
            )
            failure_code = "TARGET_IDENTITY_FAILURE" if completed.returncode else ""
            self.assertEqual(failure_code, "TARGET_IDENTITY_FAILURE")

    def test_isolated_inline_python_rejects_checkout_shadow_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            marker = workspace / "executed"
            (workspace / "secrets.py").write_text(
                "from pathlib import Path\nPath('executed').touch()\n"
            )
            process = subprocess.run(
                ["python3", "-I", "-c", "import secrets; assert len(secrets.token_hex(8)) == 16"],
                cwd=workspace, capture_output=True, check=False,
            )
            self.assertEqual(process.returncode, 0)
            self.assertFalse(marker.exists())

    def test_private_scanner_diagnostics_fail_closed_without_echoing_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            prefix = '2026-10-04T12:00:00Z\t'
            fallback = prefix + 'ERROR\t[misconfig] Falling back to embedded checks\terr=' + json.dumps(
                'failed to check cache: cache does not exist at ' + json.dumps(str(cache / 'policy' / 'content'))
            ) + '\n'
            healthy = prefix + 'INFO\tscan started\n' + fallback
            self.module.verify_diagnostics(healthy, cache)
            for value in ('', 'malformed', prefix + 'INFO\tmissing check selection', fallback + fallback,
                          healthy + prefix + 'UNKNOWN\tmessage', healthy + prefix + 'ERROR\t' + SYNTHETIC_SECRET,
                          healthy + prefix + 'WARN\tpartial scan', fallback.replace(str(cache), '/substituted')):
                with self.assertRaises(self.module.ContractError) as context:
                    self.module.verify_diagnostics(value, cache)
                self.assertFalse(SYNTHETIC_SECRET in str(context.exception))
            (cache / 'policy' / 'content').mkdir(parents=True)
            with self.assertRaises(self.module.ContractError):
                self.module.verify_diagnostics(healthy, cache)

    def test_suppressed_native_findings_fail_closed(self) -> None:
        native = native_result()
        native["Results"][0]["ExperimentalModifiedFindings"] = [{"Status": "ignored"}]
        process, result = run_evaluate_fixture(native)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["findings"], [])

    def test_gitlinks_fail_target_identity_without_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            def git(*arguments: str) -> str:
                return subprocess.check_output(
                    ["git", "-C", str(workspace), *arguments], text=True
                ).strip()
            git("init", "--quiet")
            git("config", "user.name", "SecPal Test")
            git("config", "user.email", "test@secpal.app")
            (workspace / "tracked").write_text("source\n")
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
            original = git("rev-parse", "HEAD")
            self.module.verify_target(workspace, original)
            (workspace / "linked").mkdir()
            git("update-index", "--add", "--cacheinfo", "160000," + original + ",linked")
            git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "gitlink")
            self.assertEqual(git("status", "--porcelain"), "")
            with self.assertRaises(self.module.ContractError):
                self.module.verify_target(workspace, git("rev-parse", "HEAD"))

    def test_normalization_is_independent_of_workspace_existence(self) -> None:
        native = native_result()
        native["ArtifactName"] = "/absent/authenticated-workspace"
        result = self.module.normalize_native(
            native, repository="SecPal/example", commit=COMMIT,
            workspace="/absent/authenticated-workspace",
            scanner={"name": "trivy", "version": "0.74.0", "immutable_id": "sha256:" + "a" * 64, "configuration_sha256": "sha256:" + "c" * 64},
            database=valid_database(), completed_at="2026-09-16T10:10:00Z",
        )
        self.assertEqual(result["subject"]["commit"], COMMIT)

    def test_secret_metadata_is_guarded_using_immutable_censor_masks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            secret = SYNTHETIC_SECRET
            def git(*arguments: str) -> str:
                return subprocess.check_output(["git", "-C", str(workspace), *arguments], text=True).strip()
            git("init", "--quiet")
            git("config", "user.name", "SecPal Test")
            git("config", "user.email", "test@secpal.app")
            (workspace / "secret.txt").write_text("token=" + secret + "\n")
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
            commit = git("rev-parse", "HEAD")
            native = {"Results": [{"Target": "secret.txt", "Secrets": [{
                "StartLine": 1, "EndLine": 1,
                "Code": {"Lines": [{"Number": 1, "IsCause": True, "Content": "token=" + "*" * len(secret)}]},
            }]}]}
            candidate = {"subject": {"repository": "SecPal/example", "commit": commit},
                         "gate_state": "ACTIONABLE", "findings": [{"path": "secret.txt"}]}
            self.module.verify_redaction(native, candidate, workspace, "SecPal/example", commit)
            for field in ("path", "resource", "title", "message", "package", "rule_id"):
                unsafe = copy.deepcopy(candidate)
                unsafe["findings"][0][field] = "prefix/" + secret
                with self.assertRaises(self.module.ContractError):
                    self.module.verify_redaction(native, unsafe, workspace, "SecPal/example", commit)
            (workspace / "secret.txt").write_text("modified\n")
            self.module.verify_redaction(native, candidate, workspace, "SecPal/example", commit)
            for bad in ({}, {"Lines": []}, {"Lines": [{"Number": 1, "IsCause": True, "Content": "***"}]}):
                altered = copy.deepcopy(native)
                altered["Results"][0]["Secrets"][0]["Code"] = bad
                with self.assertRaises(self.module.ContractError):
                    self.module.verify_redaction(altered, candidate, workspace, "SecPal/example", commit)

    def test_assume_unchanged_modified_bytes_fail_target_identity(self) -> None:
        self._assert_index_flags_fail_target_identity(["--assume-unchanged"])

    def test_combined_skip_worktree_and_assume_unchanged_fail_target_identity(self) -> None:
        self._assert_index_flags_fail_target_identity(
            ["--skip-worktree", "--assume-unchanged"]
        )

    def test_normalization_redacts_secret_and_preserves_all_scanner_context(self) -> None:
        observation = self.module.normalize_native(
            native_result(),
            repository="SecPal/example",
            commit=COMMIT,
            workspace=".",
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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
            workspace=".",
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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
            workspace=".",
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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
                "repository": "SecPal/example",
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

        other = copy.deepcopy(observation)
        other["subject"]["repository"] = "SecPal/other"
        self.assertEqual(self.module.admit(other, policy)["gate_state"], "ACTIONABLE")
        missing_repository = copy.deepcopy(policy)
        del missing_repository["exceptions"][0]["repository"]
        with self.assertRaises(self.module.ContractError):
            self.module.admit(observation, missing_repository)

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
            workspace=".",
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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
                "repository": "SecPal/example",
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
                workspace=".",
                scanner={
                    "name": "trivy",
                    "version": "0.74.0",
                    "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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

    def test_falsy_non_array_finding_collection_fails_closed(self) -> None:
        native = native_result()
        native["Results"] = [{"Target": "config/example.env", "Secrets": False}]
        result = evaluate_fixture(native)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")

    def test_unsupported_misconfiguration_status_fails_closed(self) -> None:
        native = native_result()
        native["Results"] = [native["Results"][2]]
        native["Results"][0]["Misconfigurations"][0]["Status"] = "BROKEN"
        result = evaluate_fixture(native)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")

    def test_non_filesystem_scanner_surface_fails_closed(self) -> None:
        native = native_result()
        native["ArtifactType"] = "container_image"
        result = evaluate_fixture(native)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")

    def test_scanner_artifact_must_match_intended_workspace(self) -> None:
        native = native_result()
        native["ArtifactName"] = "/tmp/different-workspace"
        result = evaluate_fixture(native)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")

    def test_unsupported_severity_fails_closed(self) -> None:
        native = native_result()
        native["Results"] = [native["Results"][0]]
        native["Results"][0]["Vulnerabilities"][0]["Severity"] = "EXTREME"
        result = evaluate_fixture(native)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "MALFORMED_OUTPUT")

    def test_future_database_download_fails_as_database_failure(self) -> None:
        database = valid_database()
        database["downloaded_at"] = "2026-09-16T10:11:00Z"
        result = evaluate_fixture(native_result(), database)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "DATABASE_FAILURE")

    def test_submicrosecond_future_database_download_fails_via_public_cli(self) -> None:
        database = valid_database()
        database["downloaded_at"] = "2026-09-16T10:10:00.000000800Z"
        completed, result = run_evaluate_fixture(
            {**native_result(), "Results": []},
            database,
            completed_at="2026-09-16T10:10:00.000000000Z",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(result["gate_state"], "UNKNOWN_STALE")
        self.assertEqual(result["operation"]["failure_code"], "DATABASE_FAILURE")

    def test_equal_and_prior_nanosecond_downloads_pass_via_public_cli(self) -> None:
        for downloaded_at in (
            "2026-09-16T10:10:00.000000800Z",
            "2026-09-16T10:10:00.000000799Z",
        ):
            with self.subTest(downloaded_at=downloaded_at):
                database = valid_database()
                database["downloaded_at"] = downloaded_at
                completed, result = run_evaluate_fixture(
                    {**native_result(), "Results": []},
                    database,
                    completed_at="2026-09-16T10:10:00.000000800Z",
                )
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(result["gate_state"], "CLEAN")

    def test_invalid_database_member_cannot_be_masked_via_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "core-metadata.json"
            valid = root / "java-metadata.json"
            invalid.write_text(
                json.dumps(
                    {
                        "UpdatedAt": "2026-09-16T10:06:00Z",
                        "NextUpdate": "2026-09-16T11:00:00Z",
                        "DownloadedAt": "2026-09-16T10:05:00Z",
                    }
                ),
                encoding="utf-8",
            )
            valid.write_text(
                json.dumps(
                    {
                        "UpdatedAt": "2026-09-16T09:00:00Z",
                        "NextUpdate": "2026-09-16T12:00:00Z",
                        "DownloadedAt": "2026-09-16T10:07:00Z",
                    }
                ),
                encoding="utf-8",
            )
            core_database = root / "trivy.db"
            java_database = root / "trivy-java.db"
            core_database.write_bytes(b"core")
            java_database.write_bytes(b"java")
            output = root / "database.json"
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "database",
                    "--metadata",
                    str(invalid),
                    "--metadata",
                    str(valid),
                    "--database-file",
                    str(core_database),
                    "--database-file",
                    str(java_database),
                    "--observed-at",
                    "2026-09-16T10:08:00Z",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
            )
            failure_code = "DATABASE_FAILURE" if completed.returncode else ""
            self.assertEqual(failure_code, "DATABASE_FAILURE")
            self.assertFalse(output.exists())

    def test_malformed_and_stale_evidence_never_becomes_clean(self) -> None:
        with self.assertRaises(self.module.ContractError):
            self.module.normalize_native(
                {"SchemaVersion": 2, "Results": "invalid"},
                repository="SecPal/example",
                commit=COMMIT,
                workspace=".",
                scanner={"name": "trivy", "version": "0.74.0", "immutable_id": "sha256:" + "a" * 64, "configuration_sha256": "sha256:" + "c" * 64},
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
            workspace=".",
            scanner={"name": "trivy", "version": "0.74.0", "immutable_id": "sha256:" + "a" * 64, "configuration_sha256": "sha256:" + "c" * 64},
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
            workspace=".",
            scanner={
                "name": "trivy",
                "version": "0.74.0",
                "immutable_id": "sha256:" + "a" * 64,
                "configuration_sha256": "sha256:" + "c" * 64,
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
        stale = copy.deepcopy(successful)
        stale["database"]["status"] = "STALE"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(stale, schema)
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
                    "--workspace",
                    ".",
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
                    "--workspace", ".",
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
