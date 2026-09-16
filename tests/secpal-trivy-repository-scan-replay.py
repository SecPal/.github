#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Exercise all repository scanner classes with exact pinned Trivy."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tarfile
import tempfile
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
        (workspace / "trivy.yaml").write_text(
            "scan:\n  skip-files:\n    - '**'\n",
            encoding="utf-8",
        )

        cache = root / "cache"
        native = root / "native.json"
        trusted_config = root / "trivy.yaml"
        trusted_config.write_text("{}\n", encoding="utf-8")
        subprocess.run(
            [
                str(trivy),
                "--config",
                str(trusted_config),
                "fs",
                "--scanners",
                "vuln,secret,misconfig",
                "--format",
                "json",
                "--exit-code",
                "0",
                "--quiet",
                "--skip-check-update",
                "--cache-dir",
                str(cache),
                "--secret-config",
                str(SECRET_CONFIG),
                "--output",
                str(native),
                str(workspace),
            ],
            check=True,
            env={"HOME": str(root)},
        )
        native_value = json.loads(native.read_text(encoding="utf-8"))
        completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        database = module.database_identity(
            [cache / "db" / "metadata.json"],
            [cache / "db" / "trivy.db"],
            completed_at,
        )
        observation = module.normalize_native(
            native_value,
            repository="SecPal/repository-scan-fixture",
            commit="1" * 40,
            scanner={
                "name": "trivy",
                "version": TRIVY_VERSION,
                "immutable_id": "sha256:" + TRIVY_ARCHIVE_SHA256,
            },
            database=database,
            completed_at=completed_at,
        )
        result = module.admit(observation, json.loads(POLICY.read_text(encoding="utf-8")))
        encoded = json.dumps(result, sort_keys=True)
        classes = {finding["class"] for finding in result["findings"]}
        if classes != {"VULNERABILITY", "SECRET", "MISCONFIGURATION"}:
            raise RuntimeError(f"pinned Trivy did not exercise every scanner class: {sorted(classes)}")
        if SYNTHETIC_SECRET in encoded or '"match"' in encoded.lower() or '"code"' in encoded.lower():
            raise RuntimeError("normalized evidence retained secret capture material")
        if result["gate_state"] != "ACTIONABLE":
            raise RuntimeError("representative findings were not admitted as actionable")
        print(
            json.dumps(
                {
                    "evidence_kind": "TRIVY_REPOSITORY_NATIVE_REPLAY",
                    "scanner_version": TRIVY_VERSION,
                    "scanner_identity": "sha256:" + TRIVY_ARCHIVE_SHA256,
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
