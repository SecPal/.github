# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accepted-main safety assertions for the immutable GitHub #711 tree."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


INVARIANTS = [
    "current_tree_exact",
    "historical_bytes_unavailable",
    "registered_validation",
    "source_history",
]
SCRIPT = Path("scripts/secpal-trivy-repository-scan.py")
ACTION = Path(".github/actions/trivy-repository-scan/action.yml")
POLICY = Path("policies/trivy-repository-scan-v1.json")
SCHEMA = Path("docs/schemas/secpal-trivy-repository-scan-v1.schema.json")
ACTION_TERMS = (
    "TRIVY_VERSION: 0.74.0",
    "TRIVY_ARCHIVE_SHA256: 2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a",
    "verify-target",
    "env -i HOME=\"$tool_root\"",
    "--config \"$trusted_config\"",
    "invocation_id=",
    "TARGET_IDENTITY_FAILURE",
    "DATABASE_FAILURE",
)


def _load_scanner():
    spec = importlib.util.spec_from_file_location("github_711_scanner", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("scanner module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(arguments: list[str]) -> int:
    required = (SCRIPT, ACTION, POLICY, SCHEMA)
    if arguments or any(not path.is_file() for path in required):
        print(json.dumps(["registered_validation"]))
        return 1
    try:
        action = ACTION.read_text(encoding="utf-8")
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        scanner = _load_scanner()
        try:
            scanner._severity("UNSUPPORTED")
        except scanner.ContractError:
            invalid_severity_rejected = True
        else:
            invalid_severity_rejected = False
        try:
            scanner.normalize_native(
                {"SchemaVersion": 2, "ArtifactType": "container_image", "Results": []},
                repository="SecPal/.github",
                commit="1" * 40,
                workspace=".",
                scanner={"version": "0.74.0", "identity": "sha256:" + "2" * 64},
                database={
                    "status": "FRESH",
                    "identity": "sha256:" + "3" * 64,
                    "updated_at": "2026-09-16T10:00:00Z",
                    "next_update": "2026-09-17T10:00:00Z",
                    "downloaded_at": "2026-09-16T10:05:00Z",
                },
                completed_at="2026-09-16T10:10:00Z",
            )
        except scanner.ContractError:
            wrong_surface_rejected = True
        else:
            wrong_surface_rejected = False
    except (OSError, ValueError, TypeError):
        print(json.dumps(["registered_validation"]))
        return 1
    if (
        any(term not in action for term in ACTION_TERMS)
        or policy.get("version") != "1.0.0"
        or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or not invalid_severity_rejected
        or not wrong_surface_rejected
    ):
        print(json.dumps(["registered_validation"]))
        return 1
    print(json.dumps(INVARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
