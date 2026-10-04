#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Exercise all repository scanner classes with exact pinned Trivy."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from textwrap import dedent
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "trivy-repository-scan" / "workspace"
SCRIPT = ROOT / "scripts" / "secpal-trivy-repository-scan.py"
POLICY = ROOT / "policies" / "trivy-repository-scan-v1.json"
SECRET_CONFIG = ROOT / "policies" / "trivy-repository-secret-v1.yaml"
TRIVY_VERSION = "0.74.0"
TRIVY_ARCHIVE_SHA256 = "2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a"
SYNTHETIC_SECRET = "SECPAL_SYNTHETIC_SECRET_" + "A1B2C3D4E5F6G7H8"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("repository_scan", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load repository scan module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="secpal-repository-scan-") as directory:
        root = Path(directory)
        archive = root / "trivy.tar.gz"
        request = urllib.request.Request(
            f"https://github.com/aquasecurity/trivy/releases/download/v{TRIVY_VERSION}/trivy_{TRIVY_VERSION}_Linux-64bit.tar.gz",
            headers={"User-Agent": "SecPal repository scanner replay"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            archive.write_bytes(response.read())
        if sha256(archive) != TRIVY_ARCHIVE_SHA256:
            raise RuntimeError("pinned Trivy archive identity mismatch")
        trivy = root / "trivy"
        with tarfile.open(archive, "r:gz") as bundle:
            source = bundle.extractfile("trivy")
            if source is None:
                raise RuntimeError("pinned Trivy archive lacks binary")
            trivy.write_bytes(source.read())
        trivy.chmod(0o500)

        workspace = root / "workspace"
        shutil.copytree(FIXTURE, workspace, ignore=shutil.ignore_patterns("*.license"))
        template = workspace / "synthetic-secret.txt.in"
        secret_path = workspace / "synthetic-secret.txt"
        secret_path.write_text(
            template.read_text(encoding="utf-8").replace("${TEST_VALUE}", "A1B2C3D4E5F6G7H8"),
            encoding="utf-8",
        )
        template.unlink()
        (workspace / "tests").mkdir()
        (workspace / "tests" / "example.md").write_text(secret_path.read_text())
        lock = json.loads((workspace / "package-lock.json").read_text())
        lock["packages"][""]["devDependencies"] = {"lodash": "4.17.20"}
        lock["packages"]["node_modules/lodash"]["dev"] = True
        lock["dependencies"]["lodash"]["dev"] = True
        lock["fixture_token"] = SYNTHETIC_SECRET
        (workspace / "package-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
        (workspace / "trivy.yaml").write_text(
            "scan:\n  skip-files:\n    - '**'\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
        subprocess.run(
            ["git", "-C", str(workspace), "config", "user.name", "SecPal Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(workspace), "config", "user.email", "test@secpal.app"],
            check=True,
        )
        subprocess.run(["git", "-C", str(workspace), "add", "."], check=True)
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
        module.verify_target(workspace, commit)

        cache = root / "cache"
        native = root / "native.json"
        trusted_config = root / "trivy.yaml"
        trusted_config.write_text("{}\n", encoding="utf-8")
        subprocess.run([
            str(trivy), "--config", str(trusted_config), "image",
            "--download-db-only", "--cache-dir", str(cache), "--quiet",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={"HOME": str(root)})
        scan_command = [
            str(trivy),
            "--config",
            str(trusted_config),
            "fs",
            "--scanners",
            "vuln,secret,misconfig",
            "--include-dev-deps",
            "--include-non-failures", "--show-suppressed",
            "--format",
            "json",
            "--exit-code",
            "0",
            "--skip-db-update",
            "--skip-java-db-update",
            "--skip-check-update", "--skip-version-check",
            "--cache-dir",
            str(cache),
            "--secret-config",
            str(SECRET_CONFIG),
            "--output",
            str(native),
            str(workspace),
        ]
        scanned = subprocess.run(scan_command, check=True, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, env={"HOME": str(root)})
        module.verify_diagnostics(scanned.stderr.decode("utf-8"), cache)
        generic_native = json.loads(native.read_text(encoding="utf-8"))
        generic_commit = commit
        # Keep the generic replay and add the downstream Composer development seam.
        (workspace / "composer.lock").write_text(json.dumps({
            "packages": [], "packages-dev": [{
                "name": "symfony/http-foundation", "version": "v5.4.0", "type": "library",
            }],
        }) + "\n")
        subprocess.run(["git", "-C", str(workspace), "add", "."], check=True)
        subprocess.run(["git", "-C", str(workspace), "-c", "commit.gpgsign=false",
                        "commit", "--quiet", "-m", "Composer canary fixture"], check=True)
        commit = subprocess.check_output(["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True).strip()
        module.verify_target(workspace, commit)
        scanned = subprocess.run(scan_command, check=True, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, env={"HOME": str(root)})
        native_value = json.loads(native.read_text(encoding="utf-8"))
        if native_value.get("ArtifactType") != "repository":
            raise RuntimeError("pinned Trivy did not identify the Git worktree as a repository")
        completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        database = module.database_identity(
            [cache / "db" / "metadata.json"],
            [cache / "db" / "trivy.db"],
            completed_at,
        )
        observation = module.normalize_native(
            native_value,
            repository="SecPal/repository-scan-fixture",
            commit=commit,
            workspace=str(workspace),
            scanner={
                "name": "trivy",
                "version": TRIVY_VERSION,
                "immutable_id": "sha256:" + TRIVY_ARCHIVE_SHA256,
                "configuration_sha256": module.configuration_identity(),
            },
            database=database,
            completed_at=completed_at,
        )
        diagnostics = scanned.stderr.decode("utf-8")
        if diagnostics.count("\tWARN\t" + module.SEVERITY_FALLBACK_DIAGNOSTIC) != 1:
            raise RuntimeError("Composer fixture did not exercise the exact advisory")
        module.verify_diagnostics(diagnostics, cache, native=native_value,
                                  scanner=observation["scanner"], workspace=str(workspace))
        for unexpected in ("WARN\tunknown warning", "ERROR\tparser failed"):
            try:
                module.verify_diagnostics(diagnostics + "2026-10-04T12:00:00Z\t" + unexpected + "\n",
                                          cache, native=native_value,
                                          scanner=observation["scanner"], workspace=str(workspace))
            except module.ContractError:
                pass
            else:
                raise RuntimeError("unexpected diagnostic was admitted")
        generic_observation = module.normalize_native(
            generic_native, repository="SecPal/repository-scan-fixture", commit=generic_commit,
            workspace=str(workspace), scanner=observation["scanner"], database=database,
            completed_at=completed_at,
        )
        generic_result = module.admit(generic_observation, json.loads(POLICY.read_text()))
        if generic_result["gate_state"] != "ACTIONABLE" or {f["class"] for f in generic_result["findings"]} != {"VULNERABILITY", "SECRET", "MISCONFIGURATION"}:
            raise RuntimeError("generic scanner replay regressed")
        result = module.admit(observation, json.loads(POLICY.read_text(encoding="utf-8")))
        module.verify_redaction(native_value, result, workspace, "SecPal/repository-scan-fixture", commit)
        for field in ("path", "resource", "title", "message", "package"):
            import copy
            unsafe = copy.deepcopy(result)
            unsafe["findings"][0][field] = SYNTHETIC_SECRET
            try:
                module.verify_redaction(native_value, unsafe, workspace, "SecPal/repository-scan-fixture", commit)
            except module.ContractError:
                pass
            else:
                raise RuntimeError("captured metadata bypassed the redaction guard")
        encoded = json.dumps(result, sort_keys=True)
        classes = {finding["class"] for finding in result["findings"]}
        if classes != {"VULNERABILITY", "SECRET", "MISCONFIGURATION"}:
            raise RuntimeError(f"pinned Trivy did not exercise every scanner class: {sorted(classes)}")
        if SYNTHETIC_SECRET in encoded or '"match"' in encoded.lower() or '"code"' in encoded.lower():
            raise RuntimeError("normalized evidence retained secret capture material")
        secret_paths = {f["path"] for f in result["findings"] if f["class"] == "SECRET"}
        if not {"tests/example.md", "package-lock.json"} <= secret_paths:
            raise RuntimeError("secret default exclusions remain enabled")
        if result["gate_state"] != "ACTIONABLE":
            raise RuntimeError("representative findings were not admitted as actionable")
        # Exercise the maintained action boundary itself, including both DBs,
        # health admission, redaction, public summary, and private-file cleanup.
        action_path = ROOT / ".github" / "actions" / "trivy-repository-scan" / "action.yml"
        # Extract the owned literal Bash block; this replay needs only the
        # existing vulnerability-policy dependencies on the CI runner.
        step_script = dedent(action_path.read_text().split("      run: |\n", 1)[1].split("\n    - name:", 1)[0])
        runner = root / "runner"
        runner.mkdir(mode=0o700)
        output_path, summary_path = runner / "output", runner / "summary"
        action_environment = {
            "PATH": os.environ["PATH"], "HOME": str(root),
            "GITHUB_ACTION_PATH": str(action_path.parent),
            "GITHUB_WORKSPACE": str(workspace), "GITHUB_SHA": commit,
            "GITHUB_REPOSITORY": "SecPal/repository-scan-fixture",
            "GITHUB_RUN_ID": "1123", "GITHUB_RUN_ATTEMPT": "1",
            "RUNNER_TEMP": str(runner), "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64",
            "GITHUB_OUTPUT": str(output_path), "GITHUB_STEP_SUMMARY": str(summary_path),
            "TRIVY_VERSION": TRIVY_VERSION,
            "TRIVY_ARCHIVE_SHA256": TRIVY_ARCHIVE_SHA256,
        }
        action = subprocess.run(["bash", "-c", step_script], env=action_environment,
                                capture_output=True, check=False)
        if action.returncode:
            raise RuntimeError("maintained action execution failed")
        outputs = dict(line.split("=", 1) for line in output_path.read_text().splitlines())
        evidence_root = Path(outputs["evidence-path"])
        action_result = json.loads((evidence_root / "result.json").read_text())
        import jsonschema
        jsonschema.validate(action_result, json.loads((ROOT / "docs/schemas/secpal-trivy-repository-scan-v1.schema.json").read_text()))
        if (action_result["gate_state"] != "ACTIONABLE"
                or {f["class"] for f in action_result["findings"]} != classes
                or action_result["subject"] != {"repository": "SecPal/repository-scan-fixture", "commit": commit}
                or action_result["scanner"] != observation["scanner"]
                or action_result["database"]["status"] != "FRESH"
                or action_result["policy"] != result["policy"]
                or not any(f["class"] == "VULNERABILITY" and f.get("package") == "symfony/http-foundation" for f in action_result["findings"])):
            raise RuntimeError("maintained action did not preserve Canary identities and findings")
        public = action.stdout + action.stderr + summary_path.read_bytes() + output_path.read_bytes()
        for retained in evidence_root.iterdir():
            public += retained.read_bytes()
        if SYNTHETIC_SECRET.encode() in public:
            raise RuntimeError("maintained action exposed synthetic capture material")
        if list(runner.glob("secpal-trivy-tool-*")) or list(runner.glob("secpal-trivy-cache-*")):
            raise RuntimeError("maintained action retained private scanner material")
        # Inline source suppression is rejected from immutable source before
        # Trivy can omit ignored IaC findings from its native representation.
        terraform = workspace / "insecure.tf"
        terraform.write_text("# " + "trivy" + ":ignore:*\nresource \"aws_s3_bucket\" \"insecure\" {\n  acl = \"public-read\"\n}\n")
        subprocess.run(["git", "-C", str(workspace), "add", "."], check=True)
        subprocess.run(["git", "-C", str(workspace), "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "inline ignore fixture"], check=True)
        ignored_commit = subprocess.check_output(["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True).strip()
        try:
            module.verify_target(workspace, ignored_commit)
        except module.ContractError:
            pass
        else:
            raise RuntimeError("inline source suppression bypassed central policy")
        # Some parsers report failures diagnostically while the scanner exits
        # zero. Their private diagnostics must prevent clean admission.
        terraform.unlink()
        (workspace / "malformed.tf").write_text('resource "aws_s3_bucket" "broken" {\n')
        subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(workspace), "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "malformed parser fixture"], check=True)
        failed = subprocess.run([
            str(trivy), "--config", str(trusted_config), "fs",
            "--scanners", "misconfig", "--format", "json",
            "--skip-check-update", "--skip-version-check", "--cache-dir", str(cache),
            "--output", str(root / "failure.json"), str(workspace),
        ], env={"HOME": str(root)}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if failed.returncode == 0:
            try:
                module.verify_diagnostics(failed.stderr.decode("utf-8"), cache)
            except module.ContractError:
                pass
            else:
                raise RuntimeError("parser failure fixture was admitted as healthy")
        broken_command = list(scan_command)
        broken_command[broken_command.index("--cache-dir") + 1] = str(root / "missing-cache")
        broken = subprocess.run(broken_command, env={"HOME": str(root)},
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if broken.returncode == 0:
            raise RuntimeError("missing database did not fail the scanner process")
        print(
            json.dumps(
                {
                    "evidence_kind": "TRIVY_REPOSITORY_NATIVE_REPLAY",
                    "scanner_version": TRIVY_VERSION,
                    "scanner_identity": "sha256:" + TRIVY_ARCHIVE_SHA256,
                    "target_identity_verified": True,
                    "target_commit": commit,
                    "configuration_identity": action_result["scanner"]["configuration_sha256"],
                    "policy_identity": action_result["policy"],
                    "composer_advisory_qualified": True,
                    "generic_replay_passed": True,
                    "maintained_action_passed": True,
                    "unknown_warning_fail_closed": True,
                    "parser_failure_fail_closed": True,
                    "process_failure_fail_closed": True,
                    "database_identity": database["identity"],
                    "scanner_classes": sorted(classes),
                    "secret_capture_retained": False,
                    "gate_state": result["gate_state"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
